# OAP Work Order — 206-a

PR mode: CREATE_NEW_PR
Base: main at 8d60d098b51cddb6351c6b843feb1a46db115616
Branch: oap/206-admin-numeric-display
Title: Make admin numeric displays readable and consistent

## Objective and human authority

Implement the human's small GUI fix across admin read-only numeric displays: investigate why apparent zeros appear in exponent notation, group large numbers with comma thousands and decimal dot, and show token usage/limits and other human-facing token quantities in millions of tokens. This is ordinary continuation under standing strategic OAP/merge delegation. One numeric objective maps to exactly one PR; this initial206-a creates that PR, any necessary continuation amends it. No new product/backend feature or schema.

The optional token-precision question was asked during preflight. No response arrived after a reasonable opportunity; root explicitly stated the default: e.g.937,826,734 tokens ->937.827M tokens, up to3decimal places for ordinary million-scale values with trailing zeros stripped, adaptive precision for small nonzero values, exact comma-grouped underlying count on hover/accessibility. The human's later answer overrides this default within this order; do not edit activatedorder bytes. Finish routine formatter/template/test/doc corrections within this order/PR, with no extra infrastructure or new repair order absent a demonstrated blocker.

## Verified GitHub/OAP handoff

Previous objective205 is COMPLETE. UniquePR361 merged2026-10-29T20:15:10Z as8d60d098b51cddb6351c6b843feb1a46db115616 after ALL10 final-head checks; all9 actualmain checks acrossTHREE workflows SUCCESS, rootreconfirmed now. PriorSELFfae43327af6346574fca566eb29a1b1a7b1e916c, IMPLc6f8b3fef8b4e5a1f5f289955a4e11f0667a98a0; reportonly topology verified. Sharedpre-activationactive205-f is terminal; oldrootFIFO38836 and watches13483/94678 and merge77847 CLOSED, never repoll/resignal. Rootread205-fimmutable report/STATE/timings; finalreportclericalhash/count qualifiers documented strategically, never overwritten. No unresolved205work.

Remote main8d60d098 above; sole openPR319Dependabot (leave alone), no206PR exists. Onlyreleasev0.1.0-rc.1; no release/deploy authority. Ruleset23580289 active protects defaultbranch against deletion/nonFF, no bypass. Currentcodingcheckout parked on205branch atSELFfae43327; trackedclean, untrackedCODEX-SESSIONS.md andcodex.sh protected. Agent owns all branch/Git execution and may safely begin from fresh remote main after preserving unrelatedchanges. Root never checksout/resets/stashes/cleans/stages/commits codingGit.

Use ONLY existing RIGHTtmuxpane%9, currentearly-beta/qwen3.8-27bA100(Q8)medium settings unchanged. NO helperagents/subagents/collaborationagents/model or effort change/relaunch. Nextverified solecodingwaiter422314 PPID1 argv bash wait-control-and-wake.sh, cwd=/home/janezp/codex-supervision/slaif-api-gateway, TMUX_PANE=%9. FixedtrueFIFOinodes4501469control/4501470response; rootreverifies sharedorder/active and solewaiter before ONEexactOK via canonical signal-wait-response-and-wake.sh. Read already-publishedshared206-a order/active immediately after signal; commit/push unchanged strategic-authored bytes. Preserve permanentobjective-neutral message.txt.

Protecteduntracked SHA256: CODEX-SESSIONS.md=5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda; codex.sh=66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247. Preserve ignoredconfigs/catalogs/worktrees/credentials and unrelatedchanges. RefreshliveGitHub before Gitexecution; currentfacts above are datedpreflight, not standinglaw.

## Source investigation already verified

app/slaif_gateway/db/models.py stores money/price/FX asNumeric(18,9). PythonDecimal('0').quantize(Decimal('0.000000001')) ->str '0E-9', exactlyzero; Decimal('1E-9') ispositive0.000000001, NOTzero. No epsilon/data cleanup or accounting rounding is authorized. Existing _decimal_display_filter inapp/slaif_gateway/api/admin.py (dec filter, aroundline400) usesfixedpoint/trim forDecimal only: Decimal('0E-9')->0, Decimal('-0E-9')->-0, string'0E-9'unchanged. It is used mainly inkeys/usage/import lists; keydetails/create-results/calibration, usage detail, pricing/FX and many otherreadouts interpolate raw numbers. Existingusage/detail cost expression actual_cost_eur or estimated_cost_eur incorrectly hides a present actualzero; use explicitNone handling for presentation.

69 adminHTMLtemplates exist. Search the relevantreadouts once and cover them coherently, not only theexamplekeylist. Read docs/admin-usability.md section6 andexistingtests/unit/test_admin_table_rows_194.py and browser/test_admin_usability.py fordisplayfidelity/rawsort contracts. The sharedtable-sort.js alreadycompares typedraw integers/decimals EXACTLY, including >2**53 andNumeric18,9. Do not change itsformat/parser/embeddedcatalogreport identity just to support formatted cells: retain/add rawdata-sort-value at thetemplateboundary.

## Allowed paths and boundaries

Product presentation only:
- app/slaif_gateway/api/admin.py: sharedformatter/filter registration and purepresentation helper edits ONLY; no auth/dependencies/handlers/servicecalls/DTO changes.
- optional app/slaif_gateway/web/formatting.py forsmallpure reusable formatter functions, if useful; no general rendering framework or deps.
- app/slaif_gateway/web/templates/**/*.html: onlynecessary numericreadout/units/title/aria and rawsortattribute changes, optionalsmall sharednumeric macro. Preserve forms/actions/CSRF/permissions/layout/links/IDs/branding/choicepicker/filter semantics. Not permission for unrelated UI consolidation or rewriting everytemplate.

Tests:
- new tests/unit/test_admin_numeric_display_206.py and tests/browser/test_admin_numeric_display_206.py.
- existing tests/unit/test_admin_*templates*.py, tests/unit/test_admin_table_rows_194.py, tests/unit/test_admin_usability_inventory.py, tests/browser/test_admin_usability.py and tests/browser/test_admin_visual_screenshots.py ONLY where a pre-existing literalrender expectation needs a bounded change or directly relevant reusable fixture assertion; preserve all non-presentation contracts. If another existing test legitimately fails solely due intendeddisplay, report that exactcase and make a minimal in-order oracle correction; no weakening semantic/security/sort checks.

Docs: docs/admin-usability.md numericdisplay contract; ONE docs/verification/2026-10-29-admin-numeric-display.md and itsindexentry docs/verification/README.md. Exactunchangedthisorder/oapactive206-a +ONE new oap/reports/206-a-admin-numeric-display.md.

No services/repositories/models/schema/migrations, API/CLI/CSV/JSON contracts, settings/defaults/deps/lock/workflows, provider/adapters/clientprofiles, generatedcatalogreport renderers or bundledJS/CSS/assets changes. No globalJinja finalize/DOMregex/autorewrite that can touch forms/identifiers/secrettext. A trueout-of-scope issue is reported rather than silently patched.

## Required behavior

1. Shared locale-stable numeric display. Group digitthousands with comma, decimaldot; no scientificnotation for ordinaryfinite quantities. Handle currentint/Decimal and legitimate numericDTOstrings exactly; avoid floatconversion/precisionloss forinteger64bit and9dp money. Stripunneededfractionalzeros, normalizepositive/negative actualzero to0, preserve truepositive/negative nonzero even1E-9. MissingNone never becomeszero; keep Unlimited/n/a/Unknown/Notset labels perfield. Never replace smallpositiveprices withfreezero.

2. Apply consistently to human-visible read-only quantities throughout adminGUI: requests/calls, usage/counters/limits/quota/reserved/remaining, costs/budgets/pricing/FX and numeric summaries/detail/preview/result pages where present. Use semanticformatters, not blindreplacement ofdigitstrings in arbitrary text. Identifiers/HTTPcodes/ports/dates/versionnumbers/source-row identity/rawJSON/code blocks remain literal. No changes to stored values or accounting calculations. Display actualcostzero in preference toestimate; absence alone fallsback.

3. Token quantities in M tokens consistently: used/reserved/remaining/limits, per-request/rate/capacity/headroom/calibration readouts where they are human-readable tokenquantities. Ordinarymillionvalues up to3decimals, trimzeros (1,500,000 ->1.5M tokens; 937,826,734 ->937.827M tokens). Below1M use enoughprecision to preserve smallnonzero counts (e.g.1000 ->0.001M;1 ->0.000001M), no positivevalue roundedtozero. Labelunits clearly in value or columnheading withoutduplicate tokens/M. Provide full exactcomma-grouped count through title AND accessibletext/label as appropriate; presentation approximations never become policyauthority. Already-per1M prices/rates are not token counts: keep their monetary value and existingper1M unit, neverdividepriceagain. Ifa ratewindowhassemanticunit (tokens/minute or selectedwindow), retain thatsemantic afterM conversion.

4. Raw transport/controls and sorting unchanged. Editableinput values/placeholders requiring validrawnumbers, hiddenfields, submittedpayloads, selectedoptions/queryparams, CSV/API/CLI/JSON and policy/codeexamples preserve machine/exactunits. Humanread-only summaries nearinputs may beformatted; inputlabel/help makes clear that edit stilltakes exacttoken count, not millions. Preserve omitted/null/zero semantics and numbervalidation; no new comma/M parser. data-sort-value for number/money/token columns uses canonicalungroupedunscaled exactinteger/decimal (no M, no commas), emptyforNone. Keep existingexactBigIntsort/None-last/stableties/rowordinals/headerlinks, bothdirections. Do not reuse a newlygrouped formatter in old rawsortattributes byaccident.

5. Preserve autoescaping and privacy: formatter returns plainstrings, no unsafeMarkup for arbitraryvalues; exacttitle only numericfield alreadydisplayable, no keys/secrets/metadata/rawrequestcontent added. No auth/CSRF/service/accounting/quota/replay/provider trust expansion; no backendcalls or writes triggeredbyrendering. No schema.

## Focused verification and evidence

Use focusedverification only; this is smallGUIwork, not a localfullmatrix. Reuse existingnative tests/ownedPG/browserfixture, no newharness/DBinfrastructure. NormalGitHub CI remains requiredallgreen.

- Meaningful pureformatter tests: exact0E-9/-0E-9/legitimate stringzero; true1E-9; positive/negative/fractional groupedmoney; int937826734 and >2**53/64bitbound; None/Unlimited separation; M conversion cases0,1,1000,1500000,937826734, nearroundingboundaries and no positiveaszero; no scaling pricesper1M; no floatprecisionloss/unsafeHTML.
- Render realtemplates viaASGI/unitfakes usingexistingseams: keyslist/detail andusage list/detail, pricing/FX list/detail/import summaries andrepresentativeotherreadouts; presentactualcost0vspositiveestimate; smallnonzeroprice; missingvszero; exactrawsortattributes and raweditablevalues. Update only literaldisplayoracles, keepsemanticassertions. Cover scopes not touchedby mainexamples viaactualtemplate render rather than a grep-only completenessclaim.
- Actual Chromium onexistingownedPostgreSQL fixture andrealapp/stylesheet: verifyformattedkeys/usage/detailreadouts, accessibleexactcount, comma/dot andM units; clickascending/descendingsort onrawrequests/tokens/money including distinctvalues sharinga roundedlabel and largeintegers, None-last; editcontrols retainrawtoken units andnoJS SSRformats readable. Use onebounded relevantbrowserrun, not repeatedfullbrowsersuites. Keep priorrowordinal/header/pickercontracts. New synthetic-only screenshots may go under/tmp/slaif206/ and be linked inreport, never includeplaintextsecret cells/sessionvalues orrealuserdata.
- If browserenvironment isunavailable, record exactblocker; don't callskip a pass. Do notcreatebrandnewcontainerframework. ExistinguniqueownedlabeledloopbackPG/tmpfsfixture permitted, with exactID cleanup and no ambientdatabase mutations. No fixedscratch/prune/ConfigEnv/password dumps, no realcredentials/provider/mail/production/HPC.
- RufftouchedPython, gitdiff--check, scripts/check_documentation.py andfocusedOAPgovernance9tests. Run directlyaffectedtemplate/sort/GUI tests sufficientforchanges; no unchangedCLI/provider/Codex/replay/accountingmatrices or DBconcurrencybenchmarks. Keep failures/refinements honestandwithin thisorder, no duplicateevidencefiles.

## Documentation, publication and handoff

Document confirmed0E-9source, differencefromactual1E-9, sharedformatting/locale/M precision/exacttooltips/rawformand sortlaw, no accounting/schema impact. Verificationrecord contains exactcommands/casecounts/no skips claimedaspasses, actualbrowserfacts vsmockedASGI, screenshotpaths ifproduced, safety/cleanup and limitations. Updateexistingadminusability doc onlywherecurrentnumericpresentation changes; don't rewrite historicOAPreports.

Create/pushONE206PRfromcurrentmain branch statedabove. Commitorder/active unchangedwithimplementation. PRdescription leads with observablebefore/after behavior (0E-9->0; requests937826734->937,826,734; tokens->M) andfocusedverification/no schema, notconversationhistory. Agentnevermerges/automerge.

PublishONE immutable oap/reports/206-a-admin-numeric-display.md: literal IMPL SHA; Report publication commit: SELF; finalreport-only publicationcommit firstparent=IMPL and ONLYnewreportdiffers. VerifyremotesolePRhead=SELF before signal. TreatpendingCI as pending, notpass. Include exactscope/cause/tests/browser/screenshots/truezero/nonzero/rounding/sort/form/secret/accounting evidence, docimpact andlimitations. Then sendexact2bytesOK(no newline) tofixedresponseFIFO andstartONEdetached wait-control-and-wake.sh withpane%9. No selfactivation/nextobjective/helpers/merge.

RootindependentlyreviewsimmutableSELFtopology/uniqueness/scope/materialrequirements/actualartifacts andallfinal-headchecks/reviewgates. Rootaloneguardedmergesexacthead underdelegation, thenverifiesactualmainTHREEworkflows/allrequiredchecks andrecords timings. No release/tag/deploy or productionconfigchange authorized.
