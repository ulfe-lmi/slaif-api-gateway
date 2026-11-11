# OAP Work Order — 219-c

PR mode: AMEND_EXISTING_PR

## Objective and explicit human execution override

Repair the demonstrated Chromium installation failure blocking the final GUI
completion gate, on SAME numeric objective 219 / PR376. The human explicitly
instructed the strategic model: "NO. Do it yourself. I wan't to see what the
hell is going on." Root therefore executes this bounded continuation directly,
without the coding agent, helpers or another coding process. This is a recorded
human-authorized exception to executor/Git ownership and FIFO execution handoff
for THIS round only; permanent startup authority and protocols are unchanged.
No control/response OK is sent, no new FIFO reader is opened. Existing coding
waiter stays idle. Preserve immutable orders/reports and report-only SELF law.

## Verified current state and reason

PR376 OPEN, ready, branch oap/219-gui-completion-gate, base main. Remote/local
head e5ffd607c8e759131648486db138e522c48048b4; preceding219-b IMPL
865be40f3e55032f3b0e92b15634fa687e2d0693, product34cbf03078a47ebee5a52faf5bd00a1188ec1216.
Actual main663c673494d4c0daeb4d5b1269b428ee13277448 remains unchanged.
Unrelated PR319/374 remain untouched. No new numeric objective may activate.

Exact-head CI43047324518 attempts1/2/3: other9checks SUCCESS, browser job
fails Install Chromium before tests. Jobs130614803637/130622138392/130629861588
show all26 queried runtime packages already installed; apt tries to fetch only
9additional font/Xfont packages and cannot resolve Ubuntu archive/security
hosts. The --with-deps phase fails before Chromium is downloaded. This does
not prove browser launch is impossible. Root's earlier outage-only conclusion
was premature; this order addresses the concrete installer coupling directly.

Root already downloaded a fresh matching Playwright1.65 Chromium158.0.8127.18
(build1254), FFmpeg1013 and headless shell into a NEW owned cache
/tmp/slaif219/root-chromium-install using playwright install chromium (exit0).
Actual fresh headless launch + page title/content check passed, exit0, on local
Ubuntu26.04.1. This is LOCAL proof; hosted-runner proof still REQUIRED.

## Allowed changes and required behavior

Only .github/workflows/ci.yml browser installation step; append current scoped
explanation/evidence to docs/verification/gui-cli-parity.md; this root order,
oap/active and ONE new immutable219-c report. No application/test/dependency/
schema/service/adapter/accounting/auth/replay/permissions changes. Preserve all
prior app/local/native/installed evidence, especially final19-case installed
workflow and exact source/wheel identity. No requalification of unchanged app
merely to create new receipts.

Use python -m playwright install chromium to install the matching browser.
Explicitly launch real Chromium and render/assert a minimal local page in the
same CI job before the existing full python -m pytest tests/browser -m playwright.
Use normal Playwright host validation; never skip dependency checks, ignore
launch/install failures, skip browser tests, relax assertions, suppress exit
codes, or substitute a mock. Depend on the hosted image's existing runtime
libraries only if the real launch succeeds. No DNS rewrites, apt mirrors,
external DNS services, container/runner replacement, cache/platform framework,
workflow permissions/triggers/other job changes. Missing actual runtime libs
must still fail the check clearly. Preserve existing test/service setup.

## Acceptance and verification

Fresh local download and actual rendering receipt above, then validate edited
workflow YAML and run its EXACT launch preflight with the fresh cache. Focused
OAP governance and git diff --check; confirm app bytes unchanged from final
qualified product and prior immutable artifacts/protected hashes preserved.
Normal final-head CI must run ALL required checks, including the full browser
suite on its actual hosted runner. Existing accepted461unit/4Chromium/19installed
and207-218 component evidence are reused at their exact scope, not rerun.
Report local proof separately from hosted CI; pending/skipped/failure is not pass.
If the browser-only path exposes an actual missing runtime library, inspect that
specific evidence and repair the required installation within this order/PR;
no blind rerun or speculative infrastructure expansion. Routine docs/fixture
corrections remain in this round until final publication.

## Safety, docs, publication and final gates

No production/provider/mail calls or credentials, no host apt changes needed
for the demonstrated fresh install. Synthetic local preflight only. Preserve
provider secrecy, PostgreSQL accounting, replay ownership, CSRF/review gates,
application field values and exact product scope. No release/tag/deployment.
Protected untracked CODEX-SESSIONS.md, codex.sh, uv.lock remain hash-only,
never read contents/stage/modify; preserve ignored.env/.codex/catalogs/unowned
resources. Root touches only explicitly staged paths, no reset/clean/stash/
branch switch/amend/force push. Existing branch/PR only.

Atomically publish this order/219-c pointer before edits, retain them unchanged.
Commit implementation/docs/order/pointer, create ONE complete atomic report via
same-directory temp/fsync/replace, final report-only SELF with literal IMPL sole
parent and only report diff. Push append-only; verify remote head/bytes. Record
manual execution authority and NO FIFO signals honestly. Root independently
rechecks final-head CI/review/material gates, guarded merge --match-head-commit,
actual main parents/tree and all9checks/3workflows. Maintain strategic timing
history. Full originalGUI goal is complete only after actual-main verification.
Ordinary upgrade remains application/assets restart, no schema/key migration.
