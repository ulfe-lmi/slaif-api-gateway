# OAP Work Order — 189-a

## Objective and human authority

Implement the human-requested bounded Codex additional_tools optional id compatibility fix AND an existing-key deployment upgrade path. The deployed key selects codex-0.149-responses-v1 module version4, fixture ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec. It grants codex_request_envelope, codex_client_tools, codex_streaming_tool_events, codex_encrypted_reasoning_replay and function/custom local tools. Current error responses_codex_client_tools_invalid, param input[0].id is a parser rejection, not solved by DB permissions. The user authorized implementation, focused verification and deploy instructions, not production execution or release.

PR mode: CREATE_NEW_PR
Repository: ulfe-lmi/slaif-api-gateway
Base: main at 0380f62d2bf7b57e831143801ef5532165eaddeb
Branch: oap/189-codex-additional-tools-id
Title: fix: accept bounded Codex additional-tools identifiers and upgrade pinned keys

## Verified state and required reading

188 PR326 terminal MERGED2026-10-17T01:26:01Z as currentmain0380f62, all10finalPR/all9actualmain/3workflowsSUCCESS. Prior acceptedSELFd4c5cea, immutable188-b report/order present, active188-b. Only unrelatedDependabot319 open; no189PR. Ruleset23580289 deletion/nonFF/no bypass unchanged, releasev0.1.0-rc.1 only. Sharedcheckout last188-bSELF with only untracked CODEX-SESSIONS.md/codex.sh. Preserve .codex/.local-provider-catalog/unrelatedworktrees/resources. ExistingQwenPID2075296 pane%9, solecontrolwaiter439144 verified. Agent ownsGit; root owns strategic order/active. Never rewrite message.txt or priororders/reports.

Read applicable AGENTS hierarchy, codingOAP, compact strategic architecture/OAP; AGENTIC_CLIENT_INTEGRATION.md relevant exact-profile, source/fixture, versioning5.5 and ID/privacy rules; docs/module-architecture.md, docs/codex-compatibility.md and affected Responses/LocalCoding/accounting contracts. Read current module/policy/translation/key metadata/audit/CLI/session conventions and related fixtures/tests before edits. Do not load fullrootARCHITECTURE or archives.

## Verified upstream and unresolved execution detail

Pinned0.149source openai/codex@758ef40f50c1a458425c7cfbf1eb12cbc07af0b0 (rust-v0.149.0). Root read-only cache: /home/janezp/codex-supervision/slaif-api-gateway/review-artifacts/189-a-review/upstream. models-0.149.0.rs blobba23dc2fa2a04792724b44671869d1dad1deab51 lines943ff: AdditionalTools id Option<ResponseItemId>, serde default/skip_none. response_item_id.rs blob9aa66b78da899b7589bd2ecf914c063622f2da60 is serde-transparent String, permissive historical deserialization; new IDs useprefix. client.rs blobf26d41955e59be126f3551788f5eb76dba8dd970 createsidNone and clears nonprefixed IDs before request; common.rs blobef28c6ad74d9cfedf67e8d1baa457511da2e751b carriesinput. Same optionalfield verified in0.143modelsblob46aecb61b97fe1738ff2cb6562c776a47e783c2a and0.147blob2c2a6d6b7aa49eee6309e5a9ba9e7587a1047d4e. Inspect full relevant snippets and serialization/preparation, pin tag commits for all cited versions; do not claim upstream rejects all gateway-invalid strings or blame a newerclient. Official guide https://developers.openai.com/api/docs/guides/tools-tool-search distinguishes local declarations; guide is context, pinnedsource governs this change.

IMPORTANT reproduce entire reported pipeline before assuming adding id to allowlist solves it. Current0149 taxonomy_for returnsNone and taxonomy_0148 empty; inspect module normalization/existing local-backend declaration translation to determine actual accepted omitted-id path. Do not silently make arbitrary namespaces/toolnames accepted to manufacture a passing fixture. If an additional enabling change is necessary beyond this bounded gap, report the exact blocker/paths and proposed smallest compatible change to strategy in the visiblepane BEFORE expanding scope. Keep existing finite namespace/tool validation. Do not stop merely on a routine local setup issue.

## Exact allowed paths

- app/slaif_gateway/modules/clients/codex_0149.py: version-owned optional-id vocabulary/validation policy/canonicalization and precise newmodule identity.
- app/slaif_gateway/modules/contracts.py: only a minimal default-denied policy-spec flag/field if needed; other modules retain defaults.
- app/slaif_gateway/services/responses_request_policy.py: narrow spec-driven optional-id validation/canonicalization; no scattered concreteversion checks or unrelated semantic changes.
- app/slaif_gateway/modules/servers/local_coding/adapter.py ONLY if demonstrably needed for existing declaration translation ID discard; otherwise unchanged. Do not change transport/signing/replay/accounting.
- app/slaif_gateway/cli/codex.py: narrow key compatibility-metadata upgrade/rollback command, help/docstring updated to reflect audited mutation.
- app/slaif_gateway/services/codex_module_upgrade.py (new small service): exact old/newidentity matching, keyUUID selection, locking/CAS, audit and idempotence only. May use existing models/repositories/session, no newgenericmigrationframework.
- tests/unit/test_codex_client_modules.py, test_responses_codex_client_tools.py, test_responses_codex_envelope.py, test_cli_codex.py, test_local_coding_server_module.py; new test_codex_additional_tools_id.py and test_codex_module_upgrade.py as useful.
- tests/unit/test_responses_gateway.py ONLY focused regression additions if its harness is used; tests/integration/test_codex_client_modules_postgres.py; new tests/integration/test_codex_additional_tools_id.py and test_codex_module_upgrade_postgres.py; tests/e2e/test_codex_additional_tools_id.py if actual existing E2E layout/harness permits. Additional existing harness path needs strategic confirmation beforeediting.
- tests/fixtures/codex/0.149.0/additional-tools-id-v1.json new sanitized source-derived fixture/vectors; existingimmutablecapturefixtures unchanged. Pin fixture hash/version-owned facts deliberately; current session-fixture digest may remain if explicitly unchanged with supplementalfixture separatelypinned. Do not rewrite sourcecaptures as newexecutions.
- AGENTIC_CLIENT_INTEGRATION.md, docs/module-architecture.md, docs/codex-compatibility.md, docs/responses-compatibility.md, docs/compatibility-matrix.md, docs/cli.md, docs/accounting.md: only currentidentity/behavior/upgrade guidance accurately, preservehistorical evidence.
- docs/verification/codex-additional-tools-id.md new exactproof/limits; docs/verification/README.md oneentry; docs/README.md or README.md only if necessary navigation. PreserveREADMEstopbrandblock.
- OAP unchangedthisorder/exactactive189-a and unique report.

No schema/migrations, main/config/dependency/workflow changes, credential access, UI redesign, default/0147 widening, newmodulepair/backend/platform, arbitrarypassthrough, permission redesign, toolauthority, modelcatalog change, genericID/replay redesign. Any extra path or semantic scope needs strategic decision before edit.

## Requirements and acceptance

R1 Accept omitted/null/valid optional additional_tools.id for affected0149 only. Use existing item/message-ID conventions (ASCIIbounded nonempty pattern, length, control/secretlike rejection as appropriate) consistent with string-backed upstream representation; explicitly document intentional gateway subset and maxbound, no UUID-only or invented mandatory at_prefix unless justified. Reject wrongtypes(bool/number/list/object), empty/whitespace/control/unicode/disallowed/oversize predictably with stable code and precise input[n].id. Unknownfields still fail. No value echoed/logged/stored/audited. Never fabricate IDs.

R2 Define canonicalization end-to-end. Preserve protocol itemposition/meaning; preservevalidid if existingwireforwardingrequiresit, or deliberately discard only during existing local declaration translation. Do not introduce identity/auth/replayauthority or a requestsideeffect. Test actual accepteddeclaration reachesexistingLocalbackend translation with correcttooldefinitions, no identifier leakage intoidentity/signature/audit beyond legitimateprotocolbody. Nullcanonicalization explicit. Validatebefore discard; ID differences cannot widen permissions.

R3 Preserve independentkey/route grants, function/custom allowlists, strictnamespace/toolshapes/names, description/schema/depth/totalrequestlimits, duplicate/mixeddeclaration policy, replay/HMACboundary, hostedtooldefaultdeny, PostgreSQLadmission/finalization, providercredentialsubstitution and privacy. Othermodulesretainstrictunknownid rejection unless independentlyalreadyallowed.

R4 Wirevocabulary changes require moduleversionbump percontract5.5: sameID normallyversion5, exact fixture decision recorded (currentv4 tuple above literalforupgradeselector). Staleversion4 must not be silently treatedas5. Newkeyselectionandstaticmetadataresolveexacttarget. Existingfixtureidentityprovenance honest; don'tclaimallnewerCodexqualification.

R5 Provide narrowlyscoped operatorCLI for explicitkeyUUID(s), preferably oneUUID per invocation. Defaultdryrun (or explicit safe --dry-run) plus deliberate --apply, requiredboundedreason and normalactor option for actualaudit. Exactold tuple match including id/version/fixture and malformed/extraidentityfields failclosed. Only client_module compatibilitymetadata changed; preserve everyotherkey/policy/metadata field, secret/hash/encryptedmaterial, model/provider/endpointrestrictions, expiry/status/quotas/usage/accounting. Matchcurrenttarget = safealreadyupgraded no-op; older/different/driftedidentity neverbulkupdated. UnderrowlockorCAS preserveconcurrentunrelatedpolicy/usage; audit andupdate in sameatomictransaction, rollback onfailure; dryrun no write/audit. Output/audit onlykeyUUID, old/newtuple andsafeaction/count/reason; no fullpolicies/credentials/prompts. UseexistingCLI/session/audit/DBpatterns; no schema.

R6 Rollback exacttarget->oldidentity with sameguard/transaction/audit/idempotence or a comparablynarrow documentedcommand. Explain run usingfixedbinary beforeoldbinarydowngrade, coordinatequiescence/restart acrossworkers, oldparserrejectsid again, permissionsnotreset. No automatic rollback ofunrelated policy/usage. Testdryrun/apply/repeat/mismatch/rollback/failureatomicity and preservation in realownedPG. Do notexecuteagainstdeployedDB.

## Focused verification and docs

V1 New sanitizedfixture onlypublicprovenance andsynthetic tooldeclarations/no privateprompt/credentials. Fieldstates omitted/null/valid/invalid/unknown; oldshape regression; key AND route missinggrants; function/custom restrictions; bounds/namespaces unchanged; moduleidentity stale/target; localtranslationbodychecked. Unitfakeprovideris notactualCodex/backendevidence.
V2 Relevantmodule/requestpolicy/gatewayintegrationchecks incl existingfocusedtests and regression. Use actualowned disposablePostgreSQL (existingqualifiedfixtures) for upgrade/preservation/audit/CAS and negative-admission/noaccountingeffects. Testgateway->Localtranslation usingexistingmockbackend harness withoutrealmodelcalls; stateclearlywhatran. Focuseddefault; nofull localsuite/browsermatrix/build needed. No realCodex/backendclaim unless actuallyrun namedofficialbinary against explicitlymockedbackend; no liveprovider/model authorized.
V3 RuffchangedPython, gitdiff--check, documentationchecker, canonicalorderheader/OAPstructure checks early; relevantmigrationhead check proves no schema change. FinalSELF CI gates strategic responsibility; publishaccuratereportwithpendingintermediatechecks, don't waittwobroadmatrices.
V4 Documentation includes sourcecommit/paths/serde behavior, exactmax/stringstates/errors, preserve/discarddecision, old/newmodule tuples/digests, commandsfordryrun/apply/verify/repeat/rollback, upgrade/rebuild/restartusingfixedcommit and existingCompose conventions, schemaunnecessary, gating/limitsunchanged. Distinguishunit/mockedHTTP/realPG/actualofficialCLI/realbackend/liveprovider. Neverclaimrelease/deployperformed. Reportfixedliteralcommit notvaguecurrentmain.

## Setup, privacy and publication

Reuse /tmp/slaif-181c-strategic-venv; routinelocaltoolingownedbyagent. NoambientDATABASE_URLdestructivefallback; ownedlabelledloopback/tmpfsPGfixtureswith exactID+labelcleanup only. Preserveexistingresources. Foregroundtrackedterminals forlongtests, pollcompletion. No productionDB/providerkeys/data, protectedconfig, actualemail/model/provider, release/tag/deploy. No newservice/port exceptboundedownedtestloopbackfixture.

AgentownsGit: branchfromverifiedcurrentmain, commit/pushstrategicorderandexactactiveunchanged, createexactlyone189PR, preserveunrelatedfiles. Nevermerge/auto-merge. Finaltitle/bodyreflectwholeboundedfix+upgrade. Uniqueimmutable oap/reports/189-a-codex-additional-tools-id.md withliteral Implementation head SHA: <fullSHA> and Report publication commit: SELF, source/fixture/oldnewidentity, exactcommands/results/warnings/skips/mockdistinctions, docsimpact/deviations/pending. Report-onlySELFfirstparentequalsliteralimplementation, onlyreportdiffers. VerifyremotePRhead=SELF beforeexact2bytesOKonceonresponseFIFO, thenattachsolecontrolwaiter. Strategicindependentlyreviewsguardedmerge/allfinalgates/main/timings. Nootherobjectiveuntil189terminal.
