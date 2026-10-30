# OAP Work Order — 206-b

PR mode: CONTINUE_EXISTING_PR
PR: #362 https://github.com/ulfe-lmi/slaif-api-gateway/pull/362
Base: main at 8d60d098b51cddb6351c6b843feb1a46db115616
Branch: oap/206-admin-numeric-display
Starting head: 7070bd45db499ee9a7155420ac322306910fea77
Title: Make admin numeric displays readable and consistent

## Purpose: finish the original small GUI fix

Complete the demonstrated missed readouts and fix the stale display-test oracle in this SAME PR. Do not expand supporting infrastructure, change the agreed numeric precision, or redesign the GUI. The original human request applies across GUI numeric quantities, including human-readable token/rate/margin summaries; service-built display text is not an approved exemption. Keep routine corrections in this order/PR. Only a demonstrated blocking defect warrants another repair round.

Use the existing right tmux pane %9, current early-beta/qwen3.8-27b A100(Q8) medium profile/settings unchanged. No helpers, subagents, relaunch, or model/effort changes. Root owns orders/active and merge; agent owns Git execution. No merge or auto-merge by the coding agent.

## Verified state and immutable handoff

206-a response terminal9555 is CLOSED exit0 exact RESPONSE_OK_EXACT; never repoll or resignal. Shared active was206-a. Immutable report oap/reports/206-a-admin-numeric-display.md,9390bytes,SHA2566a9f989a080bdc25c791e5efd39360a4105b2ebbba4761542e26ca3e869e485f. A order14034bytes,SHA256c1271db94f698fb8e1ca7726a8c0676848907ea33d2ae43801f450138a3f1e34. SELF7070bd45db499ee9a7155420ac322306910fea77 has first parent IMPLdc532ba3a29e628c16e87e7997801e0649ed8f97, tree5fd58ee8c9b090cebbbf64bbb385b56908f5d5b8; ONLY the report differs, verified locally and GitHub. GitHub SELF date2026-10-30T00:35:44Z. Preserve activated A order/report unchanged.

Unique PR362 OPEN/MERGEABLE, correct branch/base, no draft/auto-merge/reviews/unresolved threads. Main remains8d60d098 above. Only other open PR319; only releasev0.1.0-rc.1; ruleset23580289 remains active, no bypass. Final A checks are NOT all green: unit job failed; PG/browser pending at review, other checks green. Refresh current GitHub before Git execution and incorporate actual failures rather than ignoring them. Do not wait for an unchanged A full CI run before completing this bounded repair; final B head still needs every required check successful.

Next sole coding control waiter778846 is verified in pane%9 with cwd=/home/janezp/codex-supervision/slaif-api-gateway, argv bash wait-control-and-wake.sh. Fixed true FIFO inodes4501469/4501470. Root verifies exact shared B order/active, current GitHub and waiter before ONE control OK through canonical helper; do not open another control reader or self-activate. Preserve permanent neutral message.txt and all unrelated worktrees/configs/catalogs. Protected untracked SHA256: CODEX-SESSIONS.md=5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda; codex.sh=66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247.

## Accepted evidence to reuse

Root source-reviewed pure formatting, admin filter-only changes, zero/nonzero distinction, comma/dot grouping, exact int64/Decimal behavior, M precision, raw typed sort keys and editable raw units. Root reran the current37 new formatter/template tests:37PASS. Root read actual JUnit artifacts: unit37/0skip, earlier admin660/0skip, new actual Chromium3/0skip, existing browser10/0skip, governance9/0skip, and viewed both screenshots. Do not sum overlapping counts. Browser proof already establishes real app/owned PG/stylesheet, exact sorting of three distinct token values sharing a rounded M label, None-last, and raw input units.

Important qualification: the earlier660-unit pass predates the last zero-input representation change and is NOT a final-tree all-admin pass. Current GitHub CI40980689318, unit job123820143167 failed tests/unit/test_admin_key_actions_templates.py::test_key_detail_renders_chat_streaming_live_burn_form at line223: expected input value0.000000000, final intended value is0. Result1FAIL/6546PASS/1SKIP106.88s. Root retrieved completed-job logs directly via REST after gh --log-failed refused while the overall run was still active. This is a stale display oracle, not permission to revert correct zero normalization. Keep negative/nonzero/input-unit assertions.

## Demonstrated remaining requirements

Root made actual ASGI unit-fake-session requests (not just searches):
- Key detail with937826734 token margin displays937,826,734 instead of an M-token quantity.
- Key detail rate summary displays937826734 req/min,937826734 tokens/min without grouping or M conversion.
- Cohort detail Owners/Keys/Active keys each display937826734 without separators.

Source inspection also identified owner/institution detail counters, import preview/result summary cards across keys/pricing/FX/routes, direct token-margin readouts in usage detail, human-readable live-burn/rate summaries in key detail/create-result/import/template pages, and missing exact-count titles on cached/reasoning and stop-estimate token readouts. Complete this remaining finite set coherently, without another exhaustive inventory/report system.

1. Group remaining read-only counters/summary totals with the existing num filter. Relevant examples: cohorts/detail, owners/detail, institutions/detail; keys bulk preview/result cards; pricing, FX and routes import preview/result counts. Also apply to remaining genuine read-only numeric quantities such as retry counts/timeout/priority where present. Keep IDs, dates, HTTP codes, versions, row provenance, raw code/JSON and form transport literal. Rows-shown counters are quantities but bounded; formatting them must not break the existing JS text updates or controls.

2. Convert ALL remaining human-readable token quantities, including positive/negative token margins, configured token-rate limits and human policy summaries, to M-token display using the already-accepted precision. Preserve the original frequency/window/disabled/ignored/inheritance semantics and exact raw values; do not change rate enforcement or summary meaning. Supply exact grouped counts in titles/accessibility text for every rounded token readout (including each cached/reasoning value and stop estimates). Do not change per1M monetary prices or raw editable token units. Existing form inputs remain exact token counts; clarify edit units only where the adjacent M display could confuse them.

3. Keep this in the presentation layer. Prefer rendering already-available typed policy dictionaries with small shared template macros/pure formatters. For rate summaries where the safe DTO exposes only a service-built string, a narrowly applied pure presentation formatter for the actual finite known grammar is allowed at the template/filter boundary. Inspect its producers (admin_key_dashboard._rate_limit_policy_summary; key_import rate_limit_summary; streaming_live_burn_surface_policy_summary) and support the actual forms. Never run generic digit substitution on arbitrary text, identifiers, notes, provider metadata, URLs, raw JSON or code. Never change shared service output used by CLI/API to solve a GUI issue. No unsafe Markup; preserve autoescaping.

4. Fix the exact stale unit expectation above to0. Preserve checks that the nonzero value-0.250000000 and other nonzero digits/units remain exact, no M/comma parser is added, disabled/CSRF/action/auth behavior stays the same, and zero/None/small-positive costs remain distinct. Do not weaken assertions to merely accept both old/new rendering.

5. Remove the unapproved documentation claim that service-built human policy summaries are outside the numeric display contract. Explain the intentional raw machine/code/identifier/edit-field boundaries instead. Keep A evidence dated, qualify the stale660 pass, and add B results to the SAME verification record/index; no new parallel evidence files or retrospective rewrite of immutable reports.

## Allowed paths

- app/slaif_gateway/web/formatting.py: only necessary small pure presentation helpers.
- app/slaif_gateway/api/admin.py: filter registration/pure presentation helpers only; no handlers/auth/dependencies/service or DTO changes.
- app/slaif_gateway/web/templates/**/*.html: necessary numeric summaries/readouts/title/accessibility/raw-sort attributes and optional small shared numeric/policy macro only, preserving layout/branding/actions/CSRF/controls.
- tests/unit/test_admin_numeric_display_206.py; tests/browser/test_admin_numeric_display_206.py; tests/unit/test_admin_key_actions_templates.py; directly affected existing admin template/catalog/record/import presentation tests only for exact intended display oracles. If another direct presentation oracle fails, correct it minimally in this order; never weaken semantic/security/permission/accounting tests.
- docs/admin-usability.md; existing docs/verification/2026-10-29-admin-numeric-display.md; docs/verification/README.md.
- Exact unchanged this order, oap/active=206-b, ONE new oap/reports/206-b-admin-numeric-display-completion.md.

No shared services/repositories/models/schema/migrations, API/CLI/CSV/JSON behavior, settings/defaults/dependencies/workflows, JS/CSS/catalog report renderer identities, adapters/profiles, production changes, real provider/mail calls, or broad infrastructure.

## Focused acceptance and verification

- Add meaningful actual-template/ASGI regressions for key token margins/rate summaries, usage cached/reasoning and stop-estimate exact counts, at least one detail counter and one import summary with counts>1000, and the known human policy summaries. Exercise negative margins, None/Unlimited, true0E-9 vs1E-9, and preserved window/unit/disabled text. Do not call a grep-only survey proof of rendered behavior.
- Run the changed numeric unit file, the exact previously failing test and directly affected old presentation tests. Do NOT rerun all660 admin tests solely for unchanged cases; normal final-head CI supplies the complete regression gate. Report current-tree tests separately from earlier660 evidence.
- Extend the existing browser file/fixture minimally to demonstrate one affected key-detail rate/margin readout and usage exact-count text; run that focused browser file once after correction. Reuse A's unchanged sorting/legacy10-browser proof; no full browser matrix, new harness or huge-count DB fixture. Existing owned PG/loopback/tmpfs fixture only, exact cleanup; no ambient DB/Config.Env/password dumps/prune/fixed scratch. A screenshot may focus the actual numeric region so values are visible, with synthetic data only and no plaintext key/session fields.
- Ruff touched Python, git diff --check, documentation checker and focused OAP governance. A real failure justifies its affected correction/rerun within this order; no new round for routine oracles/prose.

## Publication and completion gates

Amend SAME unique PR362, not a new PR or objective. Update PR title/body around final observable behavior and actual evidence. Preserve A order/report and protected files. Publish unchanged B order/active, implementation and honest docs; ONE immutable B report with literal IMPL, Report publication commit: SELF, report-only SELF first parent=IMPL and ONLY the new report differs, remote unique PR head=SELF before signal. Include actual scoped results, accepted A evidence reused, stale-oracle failure/provenance, residual limitations, safe cleanup and pending checks; pending is not pass. Do not claim completion if human-readable numeric readouts remain knowingly unformatted.

Send exactly2bytes OK without newline to the verified fixed response FIFO, then start ONE detached wait-control-and-wake.sh in pane%9. No helpers or self-merge/auto-merge. Root independently reviews the full original three-part request, exact immutable topology/scope/results/browser evidence, all final-head checks and reviews, guarded-merges exact head, and verifies actual main workflows/checks. No release/tag/deploy authority.
