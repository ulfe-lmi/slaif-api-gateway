# OAP Work Order — 204-c

PR mode: CONTINUE_EXISTING_PR
Base: main at 6a523cb75b91899d1376c0ab7909404a242f44ac
Branch: oap/204-record-edits-config-inspection
PR: #360 https://github.com/ulfe-lmi/slaif-api-gateway/pull/360
Starting head: f37afaf8af2e368f7afd0a82a9b1fc699448d856
Title: Add safe owner and cohort edits and process configuration inspection

## Objective and business reason

Finish the SAME Objective204 by fixing the one observed final-head CI assertion and bounded test/documentation review issues. Preserve the fully implemented owner/cohort partial edits, safe config inspection and two task-import deferrals. ALL original204 acceptance requirements remain mandatory; root has independently reviewed B source and precisely qualified its executed evidence. No production or native-test/runtime changes are needed for this continuation. One objective/ONE existing PR; the coding agent never merges.205 all-eleven installed-executable qualification stays inactive/unproven until204 terminal and actualmain checks pass.

## Verified current GitHub/OAP state

Root consumed sole204-b response55089: CLOSED exit0 exact RESPONSE_OK_EXACT; NEVER repoll/resignal. Unique immutable B report SHA8bcde2e29d0e382e513fc57416227c968acd4c37f0123ab155b59304463a12e4, B order SHAf6e53f19dab48807e7b546456a0fe0d6476da8b53e283d6502c6ad6dac1bf44d. B SELFf37afaf8af2e368f7afd0a82a9b1fc699448d856 has firstparent IMPLeb1c5c18dd867f1a3feffbcf187f88b9dacc8291 and changes ONLY new B report; tree8ab5cf4047b2868b01d576bc583a9d406f491e3c. Implementation includes0b705bc44b483f0f92500adc3d318d3a5ff235e6 plus targeted native-test/doc proof refinementeb1c5c1. A/B orders/reports immutable. Current shared tracked tree clean at BSELF, only protected untracked CODEX-SESSIONS.md/codex.sh. PR360 uniqueOPEN on this branch/base main, no auto-merge; only otherPR319. Main remains6a523cb (203terminal/all10finalhead+9actualmainTHREEworkflowsSUCCESS). Ruleset23580289 active deletion/non-fast-forward, only releasev0.1.0-rc.1; refresh before edits. No new/replacementPR/branch or205 activation.

B final-head job123409569451/run40862529503 FAILED solely tests/unit/test_cli_record_edits.py::test_cli_owner_update_reason_is_required line775: raw literal '--reason' is split by rich ANSI styling in the usage error. Actual missing-option invocation correctly exits nonzero (SystemExit2); this is the SAME renderer-sensitive assertion class already reproduced/fixed in203-b. Broad CI count6399PASS1FAIL1SKIP. Root log /tmp/slaif204-root/final-b-unit-job.log. Pending/missing checks are not passes; re-read latest state. Root requires ALL10 final CSELF checks/THREEworkflows and review dispositions before merge.

B source/verification:74newunits0skip (42schema+21recordCLI+11configCLI),61unchanged consumers0skip,69govdocs0skip. Local native8PASS0skip at10:53:54 preceded strengthening the one late-audit case; then ONLY changed case reran against fresh ownedPG at11:01:57,1PASS0skip (overlaps8, not9unique). Native fault now really add+FLUSHes audit before exception crosses caller begin, records its ID and verifies fresh-session absence with owner rollback. Both causal lock-wait cases observed exact pg_blocking_pids relation and latest omitted fields/audits; onecase/type, no global serializability. Root actual cold-source-CLI/cached-settings/parser/service-fake/privacy/ordinary-value/clear/queue-seam rechecks pass at stable bytes, qualified in204-b-final-draft-boundary-rechecks.json and individual receipts. No installed205/backend/client/SMTP/broker/production qualification.

Root B handoff/source/evidence qualification receipt204-b-immutable-handoff-reconciliation.json; current466product/migration/settings paths and native file baseline204-c-product-baseline.json. Sole next control reader37059 PPID1/TMUX_PANE=%9 verified; true fixedFIFOinodes4501469/4501470. Root owns no coding Git manipulation. SAME rightpane/profile/model/effort, no helper models/subagents/relaunch. Read live governance/contracts and THIS complete bounded order; no architecture/runtime changes.

## Required changes (exact bounded scope)

1. Fix ONLY the new missing-required-reason assertion so it tests '--reason' in ANSI-normalized usage output using the established local pattern (tests/unit/test_cli_key_batch.py and test_cli.py). Keep nonzero-denial assertion and the actual invocation; do not remove/weaken the requirement or change CLI flags/runtime/error handling. Test-locally force typer.rich_utils.FORCE_TERMINAL=True with an appropriate stable terminal width so this condition is exercised even off GHA; strip actual ANSI escape sequences before matching. The203-b reproduction already proves old raw match false/normalized true: NO new library investigation, global renderer changes, shared fixture/helper framework or repeated console-summary runs. A tiny local helper is sufficient.

2. Address genuine code-quality thread PRRT_kwDOSLm-qM6xhWVh (comment4411541206) in tests/unit/test_cli_configuration_inspection.py: cli.main is imported with both 'import' and 'from'. Use one module import style, retaining main_cli for callback monkeypatches and the SAME app object for invocations (e.g. one module alias plus app=main_cli.app). Preserve every positive/negative/cold-subprocess/source/cached/no-secret assertion. This is test-only import cleanup, not a loader or runtime change.

3. Remove the single duplicated adjacent '## Diagnostic Logging' heading in docs/deployment.md, preserving the actual new environment/restart/recreate/Nginx guidance and all other content.

4. Correct docs/verification/2026-10-29-cli-record-edits-and-config.md evidence precision. Its current 'fresh autocommit observer' phrase is wrong: source now correctly says independent observer session that explicitly clears the statistics snapshot before each poll; default AsyncSession is not autocommit. Change prose ONLY, not transaction machinery. Separate the local8-full-file result before fault strengthening from the targeted1 corrected-case rerun; do not imply that the earlier8 run executed the later audit-insertion body. Latest CI can be reported only if actually observed on exact head, not inferred. Do not sum overlaps or rerun PG merely for prose.

The B report/live verification record also say root stored-current-canary finding was 'fixed with native regressions'. Native file covers PROVIDED note canary, not retained-current owner/cohort metadata cases. Those are UNIT + root actual-shared-service/FAKE-repository proofs. Correct the LIVE verification record and explain the immutable B report's overclaim in the NEW C report; NEVER rewrite B/A reports. Root initial fake audit capture is not proof of persisted real audit leakage: real AuditRepository also sanitizes values. The new shared guard really refuses unsafe current metadata before mutation/return/audit, and root positive/negative rechecks plus source support that behavior; keep these qualifications precise. No extra native tests are required to fix the reporting error.

Root independently reviewed the four 'statement has no effect' comments on actual awaited native updater/competitor tasks (PRRT_kwDOSLm-qM6xhWU1/WVH/WVS/WVZ). Awaits join completion/propagate exceptions and are ESSENTIAL; root resolves them as false positives with evidence. Preserve all native code. Only the import-style thread needs code correction; root owns final thread gate. Do not weaken/remove awaits or change tests to appease false positives.

## Exact allowed paths and preserved boundaries

EXISTING files ONLY:
- tests/unit/test_cli_record_edits.py (the one renderer-stable required-reason test + tiny local helper).
- tests/unit/test_cli_configuration_inspection.py (one consistent import style/binding only).
- docs/deployment.md (one duplicate heading only).
- docs/verification/2026-10-29-cli-record-edits-and-config.md (truthful evidence/provenance/C correction notes only).
- THIS strategic order unchanged, exact oap/active204-c, ONE NEW immutable oap/reports/204-c-*.md.

ALL product/migration/settings bytes and native test bytes MUST remain identical to BSELF (466path baseline plus native hash). No services/schema/config/CLI/worker/models/auth/accounting/replay/queues/providers/adapters/modules/UI/mail/runtime/dependencies/workflows changes. No new fixtures/framework/test files or changed permissions/acceptance/data. Existing complete-update and new partial/interface guards remain intact, including reason/actor, explicit clears/omission, current+provided known-shape refusal, legitimate ordinary strings, fresh locks/audit atomicity, source snapshot/restart/proxy qualifiers and default secret boundaries. No schema or key migration, production/deploy/tag/release/real provider/client/mail authority. Any demonstrated extra-path need: report BEFORE editing, do not silently expand.

## Acceptance and focused verification

Exact failing assertion passes under test-local CI-style forced ANSI and still proves missing reason denies; all assertions retained. Config test module uses the same root app/module identities, existing cases still pass. Documentation is accurate and has one Diagnostic Logging heading. Product/native bytes unchanged, all old orders/reports/protected files preserved.

Run ONLY tests/unit/test_cli_record_edits.py + tests/unit/test_cli_configuration_inspection.py together with JUnit (currently32cases), plus relevant OAP/documentation checks (the established69case gov/docs batch is suitable). Existing /tmp/slaif192-coding-venv Python3.12, units unset DATABASE_URL/TEST_DATABASE_URL, PYTHONPATH=app. Actual XML/per-file counts/exits/no skips; repository addopts suppress console summaries — do NOT rerun green tests for prettier output. Ruff changed test files, python3 scripts/check_documentation.py, git diff --check. No PG/SMTP/backend/CLI-runtime/full local matrix rerun is justified by these test-only/docs changes; ordinary finalheadCI covers broad suites. No claim all74 or8 local reran in C. Missing/pending/skipped/failed checks not passes.

## Publication and exact handoff

Reconcile remote main/uniquePR360/startheadf37afaf before Git execution; continue same branch/PR, no second204PR/new objective. Complete shared strategic order and exactactive204-c exist BEFORE ONEcontrolOK. Commit/push these exact root-authored bytes unchanged with bounded work, preserve all old transcripts and unrelated untracked CODEX-SESSIONS.md SHA5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda and codex.sh SHA66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247, ignored configs/catalogs/foreign resources. Permanent message.txt stays neutral. No merge/auto-merge or helper/relaunch/profile changes.

Inspect CI/reviews without repeated IMPL waits that final report supersedes. Publish ONE immutable C report with literal implementation SHA, `Report publication commit: SELF`, exact `Documentation updated:` statement, changed paths/precise tests/JUnit/exits/layers, renderer correction, B native/fake/observer provenance clarification, unchanged runtime/no schema/key migration/ordinary rebuild-recreate upgrade. Keep the C report concise around this delta and its evidence, referencing immutable B rather than repeating the full B implementation narrative. Product work remains B provenance; C does not claim realPG/current-client/backend/SMTP/installed205 qualification. Final report-onlySELF firstparent equals literalIMPL, only new C report differs; push/verify remote uniquePRhead before response.

Send exact TWO bytes OK ONCE to true responseFIFO, then establish/verify ONE detached next control waiter via existing wait-control-and-wake.sh, actual reader PPID1/TMUX_PANE=%9; never duplicate/read FIFOs for diagnostics (stat only). Root independently gates ALL10 final CSELFchecks/THREEworkflows +reviews/source/security/privacy/accounting/docs, guarded-merges and verifies actualmainTHREEworkflows before205. Standing ordinary continuation delegation, no new human permission needed.
