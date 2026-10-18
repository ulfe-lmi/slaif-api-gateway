# OAP Work Order — 189-b

## Objective and reason

Correct two operational documentation statements discovered in strategic review of Objective189. Runtime compatibility, PostgreSQL migration and real CLI/mock-backend proofs are accepted; no product-code change is requested. Human mandate remains optional ID plus bounded actual0.162.1 profile and safe existing-key upgrade.

PR mode: AMEND_EXISTING_PR
Repository: ulfe-lmi/slaif-api-gateway
PR: #327
Base: main at 0380f62d2bf7b57e831143801ef5532165eaddeb
Branch: oap/189-codex-additional-tools-id
Predecessor SELF: d3bee58238bc2221d24bc9901d62499e7ecbd61c
Implementation: 73fd10567a6c2558f4ec233a90ba3818745bacca

## Verified state and required reading

189-a report published immutable/report-only child with matching parent; sole response helper17996 completed and closed (do not reopen). UniquePR327 open/mergeable, base unchanged, unrelatedDependabot319 only otherPR. Nine final-head checks SUCCESS; PostgreSQL integration still running at review. No blocking human review; CodeQuality notes unused constant (harmless) and pytest fixture imports (required registration), no runtime correctness finding. Ruleset23580289 deletion/nonFF/no bypass unchanged; sole releasev0.1.0-rc.1. Active189-a; shared worktree clean except untracked CODEX-SESSIONS.md/codex.sh. Sole control reader1857996 verified. Read applicable AGENTS, coding OAP, this order, matching189-a report and the two affected paragraphs. Preserve previous order/report and strategic decisions unchanged. No full architecture/archive reading.

## Exact paths and requirements

1. docs/upgrade-runbook.md: replace the sentence claiming repeated moves fail closed. State that only the four listed transitions are supported, exact already-at-target repeats are successful no-ops without extra audit mutation, and drifted/unexpected identities or cross-target moves fail closed. Preserve dry-run/apply/rollback commands and all other operational advice.
2. docs/verification/codex-0162-local-tools.md: correct the statement that policy/admission run before provider-body construction. Request-policy validation/canonicalization precedes pure lowering; original validated declaration remains estimation input; pure body construction may precede quota reservation in the existing pipeline; actual forwarding requires successful admission; final HMAC covers final bytes; both initial and after-wait builds remain covered. No false claim of moved accounting order.
3. Commit this strategic-authored order and exact active189-b unchanged. Publish unique immutable oap/reports/189-b-migration-documentation.md in report-only SELF child of literal implementation head. Amend SAME PR327, no secondPR. PR body may clarify these facts and carry forward qualification evidence without claiming new runs.

## Acceptance, evidence and non-goals

Diff from predecessor SELF limited to two docs paragraphs, this order, active and new report. Product code, tests, fixtures, source digests and earlier immutable OAP bytes remain unchanged; verify this explicitly. Run git diff --check and applicable documentation hygiene; no runtime/unit/PG/E2E/browser/matrix reruns for prose changes. Preserve existing evidence accurately (independent503 distinct unit cases,14 realPG,3 synthetic197 Gateway/mockbackend,2 legacy E2E, actualofficialCLI realGateway/PG/mockbackend success; no real model/privateplugins/deployedfix). Pending final-headCI is not a pass.

No permissions, identity/auth/replay, provider credentials, storage, accounting/pricing/quota, schema, dependency/config/workflow/UI or otherrepo changes. No production DB/SSH/deploy/release/tag/model calls. Preserve all unrelated files/resources, message.txt, .codex/.local-provider-catalog and coding Git state; no reset/clean/stash. Use existing tools, routine owned setup only. Root owns final review/merge; agent never merges/enablesauto-merge.

## Publication and synchronization

Commit/push unchanged order and active, bounded docs implementation, report with literal Implementation head SHA: fullSHA and Report publication commit: SELF; only new report differs in SELF and first parent matches implementation. Verify remotePRhead=SELF, signal exact two-byte responseOK once, then attach sole control waiter. Strategic waits all final-head checks, guarded merges, verifies actual main checks and records timings. No190 until189 terminal.
