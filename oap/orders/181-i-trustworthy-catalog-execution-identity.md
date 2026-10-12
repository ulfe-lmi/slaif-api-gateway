# OAP Work Order — 181-i

## Objective and business reason

Close181's remaining reporting trust gaps on SAMEPR318: a supplied INTACT bundle
must not claim this review invocation fetched sources, and the report must identify
the measured catalogtool implementation beyond a packageversion. Preserve the
existing sealedfile/HMAC/descriptor boundary and human-readable oneREVIEW.html.
Use simple runner-selected context and a declared bounded code digest; no new
attestation platform, sandbox, downloader or environment/Git inspection subsystem.
Human priority is completing fixed-source refresh -> review -> atomicapply.

## Verified current state and authority

Reconciled2026-10-12T21:41–21:43UTC:
- Repo ulfe-lmi/slaif-api-gateway; mainunchanged
  6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf.
- AMEND_EXISTING_PR: unique181PR318OPEN/CLEAN/MERGEABLE,
  branch oap/181-authoritative-catalog-collection, base main/title unchanged.
- Starting immutableHreport/head8bc00b3eff405a6c5b4ee425e06bf432c972a075;
  firstparent implementation3b322d7b6178617aa4c6c2adb627189bcb396695;
  Hreport-onlypublication; all10literalreportheadchecksSUCCESS/noauto-merge.
- Active181-h exact5bytes; orderhash1902e8c9f92f2893bf26c6451ba224f664dbe8c4321f8d1f76ad9627e4ec532b;
  reporthashe01f735f2b7ce5401e2fb014544a87a86680f7fc83607ea98fb83c94ed20f333.
  Solehelper83789 RESPONSE_OK_EXACT/exit0 consumedandCLOSED; neverrepoll/resend.
- H ACCEPTED_R1_R2_TRANSPORT: worker/DeadlineStream/binding removed, actualnumeric
  publicunicast/TLS/SNI/CA/URL/redirect/proxy/encoding protections retained, late
  chunks debitedbeforefailure, standardoperatorwatchdog qualified. Independent
  205testsPASS19.11s +2watchdogPASS24.09s, parent/childDNS/socketzero, exactnegatives,
  Ruff/docs91/diffclean, public7GET qualification/identicalappcode and independent
  sealedREADYofflineverify. Keep allacceptedD/E/H behavior and these relaxations.
- Human explicitlyapprovedR1/R2, ordinaryOAP continuation remains authorized.
  I doesnot restore hardDNS/allI/O deadlines or exactwirequota promises. Resource
  processingcounts are separate from PostgreSQLmodelusage/monetary accounting.
- Strategicroot /home/janezp/codex-supervision/slaif-api-gateway; sharedrepo
  /home/janezp/codex-work/slaif-api-gateway. Panes strategic%8/pid1700208 and
  coding%9/pid1703557, session7/window0; onecodingwaiter2255103under2075296target%9.
  Reverify explicitly; tmuxdisplay withouttarget canreportfocused%8, not yourpane.
- Trackedworktreeclean, preserveCODEX-SESSIONS.md/codex.sh/.codex/localcatalogs/
  linkedworktrees/otherresources. DependabotPR319 untouched. Ruleset23580289active
  deletion/nonfastforward/nobypass; onlyprereleasev0.1.0-rc.1. No merge/newPR/
  auto-merge/release/tag/deploy/production/inference authority.
- Existing managedPython3.12.15/devvenv /tmp/slaif-181c-strategic-venv available;
  copiedcheckout.venv broken/preserve. No packages/dependencies/services needed.

Read maintained governance/protocol/compactarchitecture/currentcatalogcontracts.
Requiredread-only STRATEGIC_ROOT inputs: OBJECTIVE-181-H-STRATEGIC-REVIEW.md,
OBJECTIVE-181-CAPTURE-IDENTITY-ASSESSMENT.md INCLUDING simplicityrefinement,
review-artifacts/181-capture-review/probe.py/results.json,
CATALOG-REFRESH-IMPLEMENTATION-MANDATE.md underworkorders. Hreport's oldfuturelabels
are historical: prospective182ATOMICAPPLY/183isolatedCodex/184finalworkflow iscurrent.

## I1 execution path selects acquisition scope, never bundleJSON

Currentvalidation decides live solely from bundle.collection presence. Independent
exactFprobe reviewed an INTACT collectedbundle with HTTP/DNS/socketforbidden:
CLIstageoffline, butvalidation/HTMLclaim live_collection and 'performed by this
invocation'; verify authenticates that misleadingreport. A strippedcollection
fixture is not a regression for thiscase.

Pass runner-selected acquisition context separately from untrusted proposalJSON.
Actualcollect selects acquired-this-invocation ONLY after its collection path
executed; suppliedreview and purevalidation default offline even with intact or
fabricated collection/tool/capture fields. No CLIflag/JSONfield canpromote supplied
bytes to actualHTTP. Preserve originalcollection facts as clearly SUPPLIED prior
provenance, including dates/retrievals/inventory/digests; do not erase provenance
or renew its timestamps to solve the label. Keep source-fact/inventory/baseline/
price/FX gates intact; 'verified extraction from supplied bytes' must not imply
provider authenticity/currentHTTP that thispath never measured.

Report/CLI/validation firstscreen and details consistently distinguish current
acquisition, historical declared collection and offline suppliedreview. Collect
failures say attempted/incomplete/BLOCKED asappropriate, never invent successful
retrievals or READY. Correct stale stage wording that still says livecollection
is unimplemented; keep absentapply/Codex limitations honest. No report redesign.

## I2 authenticate original context and replay it offline

Use existing bounded authenticated artifact(s), preferably originalvalidationJSON
already included in filemanifest/HMAC, to bind runner-selected mode and generator
identity. This field is runner output, not copiedtrust from bundle declarations.
Verify authenticates captured bytes FIRST, validates supportedcontext shape/version,
then recomputes ORIGINAL artifact scope/identity to compare exactsealedreport.
Its currentexecution is always offline: explicitly noHTTP/DNS/SQL, no keycreation/
write/reseal/freshness renewal. Keep originalgenerator identity and currentverifier
identity distinct; verifying a liveoriginal is not performing a new livecollection.

Keep existing fixed file set and descriptor lineage/capture-once/aggregate limits/
no-clobber/HMAC keyoutside run andfuture researcher. No newfile or alternate signer.
A forged/mutated mode/toolidentity must fail authentication/correspondence. No
untrusted receipt/context is interpreted as authority before HMAC validation.
No claim of protection from administrator controlling the key or trustedhost.

Define explicit supportedcontext/renderer/schema versions and honestlegacybehavior.
Oldcollection artifacts lacking a trustworthy originalmode may be refused with a
safeunsupportedlegacy/version result; do not guess/relabel/rewrite/reseal archives
or build historicalrenderer fleets. Newreview of legacyPROPOSALDATA may be offline
if otherwise valid. Document exactsupport/refusal; currentfreshsealedcollect and
sealedoffline-review artifacts must verify deterministically. A currentcodehash
neednot equaloriginalgenerator if replayalgorithm/version/correspondence remains
supported; never substitute currentmain fororiginal identity or pretend refetch.

## I3 bounded measured tool identity, no broad supporting infrastructure

Two ownedcollection.py copies with differingbytes/samepackageversion produced
identical package-only code_revision. Record deterministic sourcecontent identity
for a documented FIXED small set of owned relevant catalog/schema/CLI/parser/
validator/renderer/sealing helper files (including identityhelper itself), plus
package/schema/renderer/policy/extractor versions. Relevant importedvalidation/
parser helper files may be listed explicitly. Boundfilecount/size/aggregate and
safe regularfile/error handling; no recursivefilesystem/codegraph/privatehome/
.env/config scan, environment attestation or Git subprocess machinery.

A single small execution_identity.py helper is allowed. Digestrelative logical
names+content deterministically; relocation/timestamps do notchange identity,
changedbytes/sameversion do. State measuredscope/exclusions honestly (sourcebytes,
not wholeenvironment/loadedbytecode/securityattestation). Gitcommit optionalwhere
alreadyreliablyknown from installedmetadata, otherwiseunknown is honest; package
version alone is not exactsourceidentity. Fixedrelevantlibraryversion metadata is
allowed if useful, no wholedependencytree scan. Unavailable/unsupported identity
must be explicit, never falseknown-current-main. No newdependency/versionpinning.

## Exact allowed paths and non-goals

- app/slaif_gateway/services/catalog_refresh/execution_identity.py (newsmallhelper)
- app/slaif_gateway/services/catalog_refresh/collection.py (identityintegration only)
- app/slaif_gateway/services/catalog_refresh/validation.py (scope/context/identity only)
- app/slaif_gateway/services/catalog_refresh/sealing.py (authenticatedcontext/replay/version only)
- app/slaif_gateway/services/catalog_refresh/rendering.py (scope/toolidentity/stage wording only)
- app/slaif_gateway/cli/catalog_refresh.py (runnercontext/currentverify output/stage only)
- app/slaif_gateway/schemas/catalog_refresh.py (necessary boundedidentity/version contract only)
- tests/unit/test_catalog_refresh_execution_identity.py (newfocusedhelper tests)
- tests/unit/test_catalog_refresh_collection.py
- tests/unit/test_catalog_refresh_seal.py
- tests/unit/test_catalog_refresh_report.py
- tests/unit/test_cli_catalog_refresh.py
- tests/browser/test_catalog_refresh_report.py (scope/identitylabels only)
- tests/fixtures/catalog_refresh/bundle-first-install.json
- tests/fixtures/catalog_refresh/bundle-refresh-ready.json
- tests/fixtures/catalog_refresh/bundle-blocked.json
- tests/fixtures/catalog_refresh/bundle-truncated.json
- tests/fixtures/catalog_refresh/bundle-duplicate-key.json
- tests/fixtures/catalog_refresh/report-layout/two-provider-long-ids.bundle.json
  (theseexisting JSONfixtures ONLY necessaryexplicit version/identity fields;
   preserve malformed/duplicate-key negatives and all monetary/sourcefacts)
- docs/catalog-refresh.md
- docs/cli-reference.md
- admin/catalog-refresh/README.md (currentworkflow/scope/identity/legacy wording only)
- oap/orders/181-i-trustworthy-catalog-execution-identity.md (unchanged)
- oap/active (exactstrategic5-byte181-i)
- oap/reports/181-i-trustworthy-catalog-execution-identity.md (newimmutable)

No otherpaths, newartifact set/platform/sandbox, source_transport/sources transport
redesign, source_evidence parser/billing/eligibility policies, baseline/DB/runtime
price/FX/quota/import/provider/hosted/routing mutations, dependencies/Docker/Compose/
workflows/rootgovernance/Codex execution/finalwrappers. No financial safetyrelaxation.
Ifanotherpath isessential, report concrete need beforewidening scope.

## Acceptance and proportional verification

AP-I1 actualmockedcollect -> sealedreview correctlyacquired; INTACTcollectbundle
-> suppliedreview withHTTP/DNS/SQLforbidden is offline withhistorical provenance;
fabricated/copy-pasted capture/tool fields cannotpromote. CheckCLI/JSON/HTMLlabels.
AP-I2 sealedactualcollect and sealedoffline-review verifyoffline/currentidentity
output, replayoriginalcontext/report byte-stably; modifyingcontext/tool identity
failsHMAC; unsupportedlegacy/version explicit; noarchive mutation/reseal/keyinit.
Run existingsealing/descriptor/HMAC negatives because thisboundarychanges.
AP-I3 fixedcodebytes digest/scope measured; changedbytes/sameversion differs,
relocatedsamebytes matches, nongit/dirty/project-independentCWD do not fabricate
Gitidentity; unreadable/unsupported files safe. No protectedconfig/socket use.
AP-I4 targetedofflinebrowser proof of bothscope labels/toolidentity infirstscreen/
expandeddetails; staticoffline behavior retained. Existingdenials/price/FX/source/
inventory/baseline proofs staygreen; no runtimeauthority/money changes.

Run affectedidentity/collection/seal/report/CLI/governance unit tests and targeted
browser, Ruff/docs/rounddiffcheck against8bc00b3eff405a6c5b4ee425e06bf432c972a075 and
normalGitHubCI. Do NOTrepeat full localDB/Redis/Docker matrix or sourcecollector/
proposal suites unaffectedbythisdelta. Keep mocks/DNS/socketrefusal in ordinary
unit/browser proofs, includingchildCLI. Sourceacquisition code alreadyqualifiedH;
use mockedcollect fornewcontextboundary, no newpublicGET/inference needed unless
a concretechangednetworkboundary requires renewed authorization. No physicalmodel
or protectedcredential/DB/privateconfig access. Ownprivate scratch/syntheticexternal
sealkey, neverprintsecrets/DBURLs/rawexception text. No package/service setupneeded.

AmendONLYPR318; no newPR/merge/auto-merge. Commit/push strategicorder/active unchanged
with implementation; repairin-scopeCI and verifyactualhead. Recordexactimplementation
head and Report publication commit: SELF. Beforeatomicfinalreportpath publication
ensure claims match actualevidence; finalreport thenimmutable. Report-onlySELFcommit
firstparent thatimplementationhead and changesONLYnamedreport. Push/verifyremote
PRheadSELF, sendexacttwo-byte responseOK/no newline, thenoneverifiedcontrolwaiter
explicit%9. No postpublicationedits or additionalreaders. Reportexactscope/capture/
identity/HMAC/legacy/browser/negative/DNS/test/docs/CI evidence andremaininglimitations.
No merge/no182untilwhole181accepted/allfinalheadgates. Then182atomicapply,183isolated
Codexfallback,184wholeworkflowqualification; allhumanrequirements/goalremainactive.
