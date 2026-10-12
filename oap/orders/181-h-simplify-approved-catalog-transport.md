# OAP Work Order — 181-h

## Objective, reason and human-approved contract

Simplify the fixed-official-source administrator collector on SAMEObjective181
PR318. Remove custom DNS subprocess/deadline-stream machinery and implement the
human-approved R1/R2 replacements. Preserve verified safety and truthful evidence.
This is a bounded transport closure round; runner actual-versus-intact-replay and
bounded installed tooling identity remain required in a separate later181round.
Prioritize the deterministic refresh -> REVIEW.html -> audited atomicapply path.

Human latest: "I approve replacements", after explicit accountingtradeoff
explanation. Approved R1: ordinary HTTPoperation timeouts, cooperative120-second
collection target, standardoperatorwatchdog (300s +5s KILL grace proposed), no
strictin-library DNS/allI/O elapsedtime or immediatekernelreaping guarantee.
Approved R2: bounded APPLICATION responsebody processing/counts, includingfailed/
late-returned chunks and oneboundedcrossingchunk; noexactwire/header/TLSquota.
These do NOT relax modeltoken/price/FX/accounting, sourcecompleteness, verifiedTLS,
safe actualdestinations/redirects/secrets, HMAC/anchoredI/O or atomicapply. Watchdog
is for read-onlyCOLLECT/REFRESH, NEVERapply. No realprovider inference/auth.

## Verified current state and setup

Reconciled2026-10-12T20:28–20:30UTC:
- Canonicalrepo ulfe-lmi/slaif-api-gateway, mainunchanged
  6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf.
- AMEND_EXISTING_PR: uniqueObjective181 PR318 OPEN/CLEAN/MERGEABLE,
  branch oap/181-authoritative-catalog-collection, base main/title unchanged.
- Starting immutable report/headfb2c571259af821b9b1709d40ea00893714efdc4,
  firstparent implementatione8da2b6afa26679e78e838a7fbd3ceb9391d3f47;
  publication reportonly; all10literalreport-headchecksSUCCESS/noauto-merge.
- Active181-g/orderhash0eaf1a0b92b8a51a621a1b076bec7563530b81a3f22a3fdef509c742973a23a4;
  reporthash75fa648ae166af4c3cbb05e6a4f8e52ae621f1963c46fe0b35b51e730e3c6bd5.
  Solehelper5855 exactRESPONSE_OK_EXACT/exit0 consumedandCLOSED; neverrepoll/resend.
- Gpartialreview: originalsixnegativesfixed,209affectedtestsPASS/zero parentDNS,
  actualchildcanceltest separatelyguarded/PASS, Ruff/docs91/diffclean, two sealed
  smokebundles independentlyverifyoffline; all10CIgreen. Late-returnedchunk
  omitted and customworkerlifecycle/isolationfailures found. Their old strict
  contract is now explicitly replaced prospectively; preserve transcript bytes.
- Humanapprovedcomplexityreassessment is STRATEGIC_ROOT/workorders/
  OBJECTIVE-181-COMPLEXITY-REASSESSMENT.md (including approvalsection).
- Shared roots /home/janezp/codex-work/slaif-api-gateway and
  /home/janezp/codex-supervision/slaif-api-gateway. Strategicpane%8/pid1700208,
  codingpane%9/pid1703557, session7/window0. OneidlecodingwaiterPID2217086
  under2075296 observed; reverify before reuse/no duplicatewaiter.
- Trackedworktreeclean; preserveuntrackedCODEX-SESSIONS.md/codex.sh, ignored.codex/
  localcatalogs/linkedworktrees/otherresources. DependabotPR319 untouched.
  Ruleset23580289 active deletion/non-fast-forward/no bypass. Only prerelease
  v0.1.0-rc.1; no release/tag/deploy/production authority or newPR.
- ExistingmanagedPython3.12.15/devvenv /tmp/slaif-181c-strategic-venv available;
  copiedcheckout.venv broken/preserve. Currenthost /usr/bin/timeout is uutils0.8.0,
  supports --kill-after/exit124/137; owned offlineproof in181-g-review. No new
  dependency/package/service or bespoke watchdog implementation is needed.

Read applicable maintainedconstitution/protocol, compactarchitecture, current
catalog-refresh contract, this order and read-only strategicGreview/evidence:
workorders/OBJECTIVE-181-G-STRATEGIC-REVIEW.md,
review-artifacts/181-g-review/additional_probe.py/additional-results.json,
workorders/CATALOG-REFRESH-IMPLEMENTATION-MANDATE.md. OriginalF/G exactdeadline/
wireguarantees are historical, superseded ONLY by approvedR1/R2 in this order.

## H1 smaller standard transport retaining actual destination and HTTPS protection

Remove DNSworker/script/spawn/kill/reap and DeadlineStream machinery, along with
now-unneeded deadlinebindings/private stream plumbing. Keep a small readable
connect-time global-unicast address adapter; vet the COMPLETE DNS answer set,
reject mixed/nonglobal/malformed/empty sets, connect ONLY to vettednumericIPs,
then return the library's normal stream so originalHTTPS Host/SNI/defaultverified
certificatechain/hostname policy remains. Retain explicitis_global and reserved/
multicast/mapped-address exclusions alreadyqualified. No TLS/proxy/UDS bypass.
Use ordinary systemresolver on the trustedhost; do not build a DNSsandbox, custom
HTTPclient, alternateasync stack, vendoredmodule or newcancellation abstraction.
A simple preflight guard may remain if useful; it is not the actualbinding.

StandardHTTPX connect/write/pool10s/read30s timeouts; cooperative absolute120s
checkpoint betweenattempts/chunks/phases/retrywaits. Stop before NEWapplication
activity when a checkpoint observesexpiry. Document that DNS/libraryoperations
and a continuousslowstream can exceed this target; do not claim a hardtotal
bound or automaticmid-library cancellation. No custompartialwrite/TLS/read loops
or per-DNS processes merely to preserve the withdrawn strongerguarantee.

Preserve exactURL/pathfamilies, validquotedmodelIDs, traversal/malformedport
rejection, manualboundedredirects, fulltargetrevalidation, safe lastvalidatedURL
provenance, safeerrors, trust_envFalse and identity-onlyencoding refusal BEFORE
expansion. Sourcebodies are inert parsed data, no provider/gateway/seal/DBsecrets
are sent. Fixedregistry prevents arbitraryremote URLs/configuration authority.

## H2 honest bounded application body accounting

Retain one invocationownedattempt/body/cache context acrossallphases, redirects,
retries and failedretrievals. Keep128attempt/32MiB defaults/per-kindcaps/bounded
read buffers. Count RETURNED applicationbodychunks, not network/TLS/header bytes
or unseen internalprefetch. Debitevery returnedchunk BEFORE deadline/overflow
failure, including chunks arriving afterexpiry; record crossingdeficit and
terminalexhaustion honestly, neverrefund. Application checkpoints BEFORE requesting
anotherchunk and after processing keep cooperation honest. No laterprocessing/
request after terminalexhaustion; preserve validexact-fit completion/EOF semantics.
Never use Content-Length as proof of completeness or an excuse to acceptpartial
source. Preserve cache/specidentity and completebody/hash/capturedbytes agreement.

ExactGnegative:256context,200returned, expires,100returned -> actualprocessed300,
charged300, remaining-44/exhausted; mayraise safe deadline/budgetcode, but mustnot
retain56credit or omit100. Existing Gtest with200+10 returned afterdeadline must
count210, not its misleading old200 assertion. Already-consumed bytes passed to
charge_body_bytes cannot vanish just because the deadline has elapsed. Require
focusedregressions for this and failedread/overflow/cross-phase reuse. Allow one
boundedcrossingchunk before refusal; neverclaim exactnetworkbandwidth enforcement.
If attemptmetadata claims actualHTTPrequests, ensure rejectedpreflight/redirect
validation is not counted as a sentrequest; conservative budgetreservation may
remain but mustbe describedaccurately without a newmetrics subsystem.

## H3 standard operator watchdog, no new supporting infrastructure

Document/support one watchdog-prefixed read-onlycollection command using existing
OS timeout: default300seconds with5-second --kill-after grace around
slaif-gateway catalog-refresh collect <ordinaryarguments>. This is still one
administratorcommand. Operator can choose an explicit positivefinite duration;
no newCLIflag/envconfig parser or wrapperframework is needed thisround. Final
administratorwrapper will integrate the samewatchdog later. Never wrap apply,
imports, database mutations or OAP coding execution in thiscollectwatchdog.

Missingutility/timeout124/KILL137/error statuses mustremain non-success; interrupted
runs mustnotbe reported as freshREADY or overwrite an olderreview. Existingatomic
publication protects incomplete/stagingoutput: cancellationmayproduce no final
report, and incomplete/unsealedruns cannot later be applied. Do not invent a fake
sealedBLOCKED report afterSIGKILL, automaticallyretry, or treat existingarchive as
thisinvocation's success. State Linux/operatorenvironment support honestly.

Qualify the documented watchdog with an owned subprocess driving actualcollect
against mockHTTP/DNS that stalls (including a TERM-ignoring ownednegative), short
injectedtestdurations only, noprivateservice. Verify boundedpracticalreturn/status,
no newcompletedREADY from interruptedacquisition, earlierpublishedruns unchanged,
noDBmutation/inference/apply. Use the existingstandardutility, not a handcrafted
Pythonprocesssupervisor. Noplatformmatrix or kernel-hardrealtime promise.

## Exact allowed paths and non-goals

- app/slaif_gateway/services/catalog_refresh/sources.py
- app/slaif_gateway/services/catalog_refresh/source_transport.py
- app/slaif_gateway/services/catalog_refresh/collection.py (client/budget lifecycle only)
- tests/unit/test_catalog_refresh_sources.py
- tests/unit/test_catalog_refresh_collection.py
- tests/unit/test_cli_catalog_refresh.py (watchdog/cancellation/source regression only)
- docs/catalog-refresh.md (approvedtransport/body/watchdog guarantees/limits only)
- docs/cli-reference.md (collectwatchdog/status wording only)
- admin/catalog-refresh/README.md (supportedcollectwatchdog/status/limits only)
- oap/orders/181-h-simplify-approved-catalog-transport.md (unchanged strategicbytes)
- oap/active (exact strategicfive-byte181-h)
- oap/reports/181-h-simplify-approved-catalog-transport.md (new immutable)

Nootherpaths. No newscript/service/dependency, DB/schema/runtimepricing/FX/quota/
accounting/routing/hostedpolicy/import, parser/baseline/eligibility changes, report/
bundle/capture/seal/identity redesign, Docker/Compose/workflows/rootgovernance,
Codexresearcher or finalwrapper. Remove obsolete machinery-specific tests; retain
all corresponding safety/body/source/data-integrity regressions under newcontract.
If an extra path is essential, report the exactneed before widening scope.

## Acceptance, proportional verification and publication

AP-H1 customDNSworkers/DeadlineStream absent; smallnumericbindingadapter retains
TLS/SNI/defaultCA/globalunicast/mixedset/proxy/redirect/URLnegatives at ACTUAL
connectionseam. HTTPX standardstream/timeouts own normalI/O. No fauxDNSisolation.
AP-H2 late/failed/crossingchunks counted beforefailure; finitecontext/cache spans
allphases; no postexhaustion requests; identityencoding rejected beforeexpansion;
partial/malformed/errorretrieval cannot become READY/deletion/bootstrap.
AP-H3 documentedwatchdog qualified with actualmockedcollect subprocess, timeout/
TERM-ignore negatives/non-success status/incompletearchiveproof. Directrawcollect
limitations explicit. Noapply/database/provider monetary change.
AP-H4 docs/report accurately stateapprovedrelaxations, preservation of essential
security/data/monetary boundaries and remainingcapture/toolidentity/fullworkflow.
Run affectedsource/collection/CLI/governance tests, Ruff, docscheck and rounddiff
againstfb2c571259af821b9b1709d40ea00893714efdc4; normalGitHubCI. OrdinarytestsHTTP/
DNS/socketmocked/denied, including spawnedCLI via ownedtestharness. No full local
DB/Redis/Docker/browser matrix; no repeatunaffectedfocusedfiles justforcounts.

Because actualtransportchanges, on literalpushedimplementationhead qualify bounded
productiontransport publicGETs: OpenAI/OpenRouter/neededECB plusone actualOpenAI
modelpage, selecteligiblemodel fromfetchedcurrentfacts. Max24HTTPattempts/8MiB
processedbody/120s watchdog perinvocation, lowerper-sourcecaps; noalternateclient,
protectedauth/inference/DB. Use headG knowneligible scope as a hint, not stalefacts;
avoid repeatedly trying alreadydisqualified legacycompletionmodels. Retain safe
status/hash/attempt/processedbyte/timing/codehead fingerprints and selectedreport.
Verifysealedrunoffline withHTTP/DNS/socketforbidden, external synthetickey outside
run. No requirement to repeat historicalqualification without a changedboundary.

AmendONLYPR318, nevermerge/auto-merge/newPR. Commit/push unchangedstrategicorder/
active withimplementation. Inspect actualCI/repair in-scope failures. Beforeatomic
finalreportpublication ensure claims match evidence; preserve failed/pendinglimits
honestly. Reportliteralimplementationhead and Reportpublicationcommit:SELF;
atomicfinalpathmakesreportimmutable. Finalreport-onlycommit firstparent thathead,
changesONLYthisreport; push/verify remotePRheadSELF before exacttwo-byte responseOK
(no newline). Then exactlyonecontrolwaiter onverified%9. No postpublicationedits.
Reportcode reduction, R1/R2approval, connection/body/watchdog tests/smoke/offline/
DNSaudit/docs/CI/setup/scope and remainingreportidentity/fullworkflow. Capture/
intactreplay/exacttoolidentity remain REQUIRED later181; no merge/no182 untilwhole
181accepted. Prospective182atomicapply/183isolatedCodex/184completeworkflow remain
required; historicalorders/reports retain their originalmapping unchanged.
