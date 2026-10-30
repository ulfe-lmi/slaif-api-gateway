# OAP Work Order — 206-d

PR mode: CONTINUE_EXISTING_PR
PR: #362 https://github.com/ulfe-lmi/slaif-api-gateway/pull/362
Base: main at 8d60d098b51cddb6351c6b843feb1a46db115616
Branch: oap/206-admin-numeric-display
Starting head: 39c045c3c507ba558232dd491effe2bfdb699bad
Title: Make admin numeric displays readable and consistent

## Exact purpose and authorization

TEST-ONLY correction of the two stale display expectations reported in206-c. Root accepts the actual GUI implementation and authorizes editing the previously-out-of-scope integration test now, under the original human GUI-fix mandate. No new human approval is required for this routine oracle correction. No product code, template, shared formatter, infrastructure, or policy change is permitted. Finish this in SAME PR362, preserving all accepted A/B/C evidence and immutable orders/reports.

## Verified handoff/state

C response27740 CLOSED exit0 exact RESPONSE_OK_EXACT; never repoll/resignal. C immutable report oap/reports/206-c-final-numeric-captions.md9623bytes,SHA256284e51e4cc1c1b44003ecefca96b56be520f6c21d92143df9db433eb1dfb9e64. C order7811bytes,SHA256e37dbcf82474181aff77265ace9234b569851841f1e371139af67b478b97dd30. SELF39c045c3c507ba558232dd491effe2bfdb699bad first parent IMPL696518cfa4d37431c7052dd711dcbc036385395d, tree9b094bc71653cda1acad4f9ac6b0edf37a79bcf7; ONLY C report differs, rootverified local/GitHub. GitHub SELF date2026-10-30T01:51:49Z. Preserve all earlier reports/orders unchanged.

UniquePR362 OPEN/MERGEABLE, no auto-merge/reviews/unresolved threads; main8d60d098 above; sole other openPR319; onlyreleasev0.1.0-rc.1; ruleset23580289 active/no bypass. Current C CI pending at handoff; it inherits the known PG oracle failure. Refresh GitHub before execution; pending/missing/skipped is not pass. Do not wait for another unchanged C full PG failure before fixing this known deterministic oracle. Final D head must have every required check successful before merge.

Root independently retrieved B PostgreSQL job123835904685 logs (run40985644692):1FAIL/519PASS/9SKIP933.39s, test_admin_catalog_readonly_pages expected'0.100000000' after accepted GUI formatting changed it to'0.1'. The same unchanged file also expects'0.920000000' in FX detail, now'0.92'. These are display literals only. C correctly preserved scope and reported them; this order resolves that scope conflict.

## Exact allowed edit

In tests/integration/test_admin_catalog_readonly_postgres.py::test_admin_catalog_readonly_pages:
- Replace the old padded pricing-detail expectation at line227 with an exact assertion for `<dt>Input / 1M</dt><dd>0.1</dd>` (normal whitespace permitted via existing re if useful).
- Replace the old padded FX-detail expectation near line246 with an exact assertion for `<dt>Rate</dt><dd>0.92</dd>`.

Keep fixture Decimal values0.100000000/0.920000000 and ALL other assertions, persistence, auth, filtering, secret guards and setup unchanged. Bind each new expectation to its actual named readout; do not weaken to a generic'0.1'inwholepage assertion or accept both old/new forms. The existing re import is sufficient. Do not revert product formatting to satisfy the old test.

Other allowed paths: exact unchanged this D order, oap/active206-d, ONE new oap/reports/206-d-numeric-display-integration-oracles.md, and a SHORT D results note appended to existing docs/verification/2026-10-29-admin-numeric-display.md (README verification index only if necessary). No new verification document. No app/, templates, settings, migrations, services, JS/CSS, formatter, unit/browser files, conftest, dependencies or workflow changes.

## One focused verification, reuse everything else

Run ONLY the affected native PostgreSQL test case in an owned disposable PG16 environment,0skip. Reuse the already-qualified existing owned fixture tests.integration.test_lazy_throttling_postgres_redis.owned_pg_url: its undecorated generator via __wrapped__ takes no arguments, creates a unique owned labeled loopback/tmpfs PG, verifies ownership, migrates, yields a test URL, and exact-ID cleans up in finally. A tiny transient command may open that existing generator, pass its returned URL as TEST_DATABASE_URL to a child pytest for this one node, and close the generator in finally. This is reuse of the existing fixture, NOT permission for a new source fixture/harness/helper file. Scrub ambient DATABASE_URL/TEST_DATABASE_URL and real provider credentials, keep APP_ENV=test, never print URL/password or Config.Env. Retain only JUnit/counts and exact owned-container cleanup facts. No broad prune/fixed scratch/shared DB.

If that existing safe fixture genuinely cannot run, report the concrete blocker without bypass, and rely on the final-head GitHub PG gate for the actual case; never call a local skip a pass. Do not introduce another database setup framework. No real provider/mail/production calls.

Ruff touched Python, git diff --check, documentation checker and9 OAP governance tests. Do NOT rerun60/309/16 unit groups or any browser/CLI/Codex/provider/Redis/accounting matrices: accepted A/B/C proofs are unchanged. Root C actual-render6PASS, C60/16/gov9PASS and A/B browser/exact-sort/formatting proofs remain accepted. Normal final-head CI provides the complete regression gate.

## Publication and completion

Use ONLY existing RIGHT tmux pane%9/current early-beta/qwen3.8-27bA100(Q8)medium settings. No helpers/subagents, relaunch or model/effort changes. Verified next coding control waiter860368 cwd=/home/janezp/codex-supervision/slaif-api-gateway, argv bash wait-control-and-wake.sh, TMUX_PANE=%9; fixed FIFO inodes4501469/4501470. Root verifies complete shared order/active and sends ONE exact controlOK using the canonical helper. No duplicate reader or self-activation.

Preserve permanent neutral message.txt, unrelated local worktrees/configs/catalogs and protected untracked CODEX-SESSIONS.md SHA5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda and codex.sh SHA66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247. Agent owns Git and never merges or auto-merges. No second206PR/new objective.

Commit/push unchanged D order/active with the tiny test/docs correction. PR description should concisely describe final user-visible before/after behavior and actual verification, not repeat the conversation or unresolved stale-oracle history. Publish ONE immutable honest D report: literal IMPL SHA; Report publication commit: SELF; report-only SELF first parent=IMPL and ONLY the new report differs; remote unique PR head=SELF before signal. Include exact one-case result/cleanup or blocker, reused evidence, source-scope proof and pendingCI. No release/tag/deploy claim.

Send exactly2bytesOK without newline to fixed responseFIFO, then start ONE detached wait-control-and-wake.sh in pane%9. Root independently verifies immutable topology, test-only diff and original3-part GUI goal evidence, ALL final-head checks/review gates, guarded-merges exact head and verifies actual-main workflows/checks. No more product edits or infrastructure are needed for this order.
