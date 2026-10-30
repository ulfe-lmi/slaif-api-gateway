# OAP Work Order — 206-c

PR mode: CONTINUE_EXISTING_PR
PR: #362 https://github.com/ulfe-lmi/slaif-api-gateway/pull/362
Base: main at 8d60d098b51cddb6351c6b843feb1a46db115616
Branch: oap/206-admin-numeric-display
Starting head: e31a0d38b4929a2a5355c6f54bc890a2c3e19fde
Title: Make admin numeric displays readable and consistent

## Tiny final correction, not another subsystem

Finish the original GUI-number consistency request by correcting the five remaining templates listed below. Reuse the existing num filter and all accepted 206-a/b evidence. No new formatter, policy parser, service, browser run, database fixture or infrastructure. Keep routine literal-oracle/prose corrections in this order/PR; finish and publish only when the stated examples render correctly. Do not perform another broad inventory or re-run unchanged suites.

## Verified handoff

206-b response22453 CLOSED exit0 exact RESPONSE_OK_EXACT; never repoll/resignal. Immutable report oap/reports/206-b-admin-numeric-display-completion.md,14119bytes,SHA2560ab9eeb9b61e85edcc551cae22cb7a06da5c6d8a0764a0e9f90dac8f483aad98. B order12020bytes,SHA2564b52e2e86b561a298eae8c18327f2ed116daae4dc063e8b789d0c4ff0413c64f. SELF e31a0d38b4929a2a5355c6f54bc890a2c3e19fde first parent IMPL f85f6c09ccc4191f12a8c48dd7bb1744add69726, tree b9686b80c0fcca137a87ebfef1c83358696525dd; ONLY the B report differs, independently verified local/GitHub. GitHub SELF date2026-10-30T01:23:53Z. Preserve all earlier activated orders/reports.

Unique PR362 OPEN/MERGEABLE, correct branch/base, no auto-merge/reviews/unresolved threads. Main8d60d098 above; only other open PR319; only releasev0.1.0-rc.1; default-branch ruleset23580289 active/no bypass. Latest B head9 checks SUCCESS, PG integration pending, no failure. Refresh current GitHub before execution; pending is not pass, and the final C head still needs ALL final checks.

Root reran54 numeric tests plus the previously failing stale-zero-oracle test:55PASS. Actual ASGI probes confirm key rate/margin M formatting, cohort grouping, exact raw edit units; actual shared producer summaries confirm0E-9 zero, true1E-9 nonzero, and negative margins. Root read B54/309/3-browser JUnit,0skip; A core raw-sort/legacy browser evidence reused. Main presentation and policy helpers are accepted. Do not re-prove them or change them.

Remaining defect is concrete: root ASGI GETs /admin/usage and /admin/audit with default Settings both visibly show "capped at 10000 rows". usage/detail.html still uses `usage.latency_ms or "n/a"`, so a real zero latency becomes missing and a large latency stays ungrouped. Source also shows three remaining human quantities in the assisted-result summary (rows, TSV bytes, byte ceiling) and template default validity days. These are read-only quantities, not IDs or raw transport.

## Exact edits and acceptance

1. app/slaif_gateway/web/templates/usage/list.html and audit/list.html: render visible export_max_rows using num, so default10000 ->10,000. Hidden controls, CSV parameters and actual ceilings remain exact/unchanged.
2. app/slaif_gateway/web/templates/usage/detail.html: render latency with explicit None handling and num, preserving ms units:0 ->0 ms,1234567 ->1,234,567 ms,None ->n/a ms. Never use truthiness to treat an actual zero as missing.
3. app/slaif_gateway/web/templates/openai_assisted/result.html: use num for visible result.row_count, warnings length, import_bridge.tsv_bytes and max_bytes. Keep generated TSV/textarea contents, links, source labels and payloads byte-for-byte; no OpenAI/provider call.
4. app/slaif_gateway/web/templates/templates/detail.html: format the read-only validity_days_default with num when present, retaining Not set for None; actual edit/form policy units unchanged.

No further UI redesign or generic digit rewriting. Source-row identity, dates, HTTP/status codes, versions, raw code/JSON and editable/hidden/query values stay literal. Existing M-token precision, exact-count titles, true-zero/small-positive handling, raw sort keys and all auth/CSRF/accounting/privacy boundaries remain unchanged. Plain strings/normal autoescaping, no unsafe Markup.

## Allowed paths

Only the five template paths above (usage/list, audit/list, usage/detail, openai_assisted/result, templates/detail), tests/unit/test_admin_numeric_display_206.py for small actual-render regressions, and directly affected existing tests/unit/test_admin_openai_assisted_catalog_routes.py / test_admin_activity_templates_safety.py only if a literal intended-display assertion needs adjustment. Preserve all semantic/security assertions. Do not edit admin.py, formatting.py, services, DTOs, models, migrations, settings, JS/CSS, dependencies, workflows or any transport/API/CLI/export contracts.

Docs: append a SHORT dated C result/caption note to the existing docs/verification/2026-10-29-admin-numeric-display.md and update its README index only as needed. Existing docs/admin-usability.md may get one sentence for latency/caption consistency; do not rewrite A/B evidence or create another verification file. Exact unchanged this order, oap/active206-c, and ONE new oap/reports/206-c-final-numeric-captions.md.

## Focused checks only

Use existing unit ASGI seams; add direct real-template/ASGI checks for the two default export captions10,000, latency0/large/None, and representative assisted-result row/byte readouts and unchanged raw TSV. Check validity-day num/None through an existing render seam or a small actual-template test. No new browser execution is needed for these text-only existing-filter applications; reuse accepted B Chromium proof and A exact-sort/legacy evidence.

Run the changed numeric unit file and the directly affected existing presentation files needed by these edits, plus Ruff touched Python, git diff --check, docs checker, OAP governance. No660/309 full repeat, no provider/CLI/Codex/Redis/accounting matrix. A genuine failure warrants its focused correction within this order. Report actual current-tree counts separately from reused A/B proof, no summed overlap or skipped-as-pass claims.

## Execution, publication and gates

ONLY existing RIGHT tmux pane%9, current early-beta/qwen3.8-27b A100(Q8) medium/settings unchanged. No helpers/subagents/relaunch/model changes. Verified next coding control waiter843152, cwd=/home/janezp/codex-supervision/slaif-api-gateway, TMUX_PANE=%9, argv bash wait-control-and-wake.sh; fixed FIFO inodes4501469control/4501470response. Root verifies complete shared order/active then ONE exact control OK through canonical helper. Do not start another reader or self-activate.

Preserve neutral permanent message.txt, unrelated local worktrees/configs/catalogs and protected untracked CODEX-SESSIONS.md SHA5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda and codex.sh SHA66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247. Agent owns Git execution and never merges/auto-merges. Amend SAME unique PR362; no new PR/objective or production/release authority.

Commit/push unchanged C order/active with the tiny implementation/docs. Publish ONE immutable C report: literal IMPL SHA, Report publication commit: SELF; report-only SELF first parent=IMPL, ONLY this new report differs, remote unique PR head=SELF before signal. State exact scoped results, reused A/B proof, pending CI, source scope/no schema, honest limitations. Send exactly2bytesOK without newline to fixed response FIFO; start ONE detached wait-control-and-wake.sh in pane%9. No extra order for routine correction.

Root independently reviews the entire original three-part display goal using accepted A/B evidence plus these final corrections, immutable topology and final-head checks/reviews, then guarded-merges exact head and verifies actual-main workflows/checks. No tag/release/deploy.
