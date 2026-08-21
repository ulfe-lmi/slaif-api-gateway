# OAP Work Order — 022-e

PR mode: `CONTINUE_EXISTING_PR`

## Objective and reason

Finish the non-live preparation for Objective 022 on PR #248. The real target
runner now uses Codex→SLAIF→provider, but it still starts an unused mock and
requires the loopback mock's exact `(1 input, 1 output)` usage/cost values. A
valid live vLLM response therefore cannot pass. Make live accounting bounded
and usage-driven, preserve exact hermetic assertions, and clear two new review
comments. No actual LAN call is possible while variables are absent.

Implement immediately; do not reopen architecture, database provisioning,
taxonomy, or broad test discovery.

## Verified continuation state

- `main` is `4ad592e190f6bfa1a8878814519569b6ce7e59a2`.
- PR #248 report head is
  `e42e7dc661986016b2493463022941e4bc7b3e6c`, first-parent implementation
  `d87f7a9be46199b3d2f5c27a0a8bc742061b358e`.
- Hermetic and configured-provider loopback plumbing phases pass. Candidate is
  mocked-conformant, unregistered, live-false. Live variables remain absent.
- Authority scanning is active for every 0.148 tool; only the captured
  `exec_command...shell` and `request_user_input...header` key paths are
  allowlisted. Do not widen them.
- Two unresolved code-quality threads flag mixed import styles in
  `test_qwen38_text_codex_candidate.py` and
  `verify_qwen38_text_codex.py`.
- `oap/active` is `022-e`. Amend PR #248 only; never merge or auto-merge.

## Allowed paths

```text
scripts/verify_qwen38_text_codex.py
tests/unit/test_qwen38_text_codex_candidate.py
docs/codex-compatibility.md
docs/configuration.md
oap/active
oap/orders/022-e-qwen38-text-codex-qualification.md
oap/reports/022-e-qwen38-text-codex-qualification.md
```

One exact adjacent verifier helper path is allowed only if required by a
concrete imported type and must be reported. No runtime policy/registry/schema
change is authorized in this round.

## Required corrections

1. Do not construct/start `ScriptedOpenAIMock` in the human-LAN path. Create and
   queue it only for the hermetic or explicit local-plumbing modes. A real live
   target has no loopback fallback or unused listener.
2. Keep the hermetic mode's exact two requests, per-ledger usage
   `(1,0,1,0,2)`, EUR `0.000003000` each, key totals, statuses, and fixture
   assertions unchanged.
3. Seed the live mode with explicit complete **local-zero pricing** for the
   exact provider/model/Responses route. Require exactly one serial tool turn
   and final turn, supported final usage on both responses, positive bounded
   per-request/aggregate token counts within the finite key/profile caps, two
   finalized successful ledgers/reservations, key token/request totals equal to
   ledger usage sums, all key/ledger/reserved EUR costs exactly zero, no pending
   reservation, and no error status. Do not compare live usage to mock constants.
4. In local live-plumbing mode, exercise this same live accounting branch with
   the configured numeric-loopback target and prove zero-pricing dynamic
   reconciliation. Keep its claim explicitly plumbing-only.
5. `REAL_PROVIDER_CALLED=true` and `LIVE_EVIDENCE_PASSED=true` require completed
   Codex file/final markers plus the live accounting/privacy checks. Failure or
   missing usage emits fixed failure and keeps both false. Continue emitting
   exactly one `LIVE_QUALIFIED=false` until the later evidence/promotion commit.
6. Fix both mixed-import findings without suppressions; resolve their threads
   only after correction and check for new threads.

## Non-goals

No LAN call with absent variables, registry promotion, vision, policy/catalog
redesign, hosted tools, migration, release claim, or full local suite.

## Acceptance and verification

- Focused pure tests prove hermetic fixed accounting and live dynamic local-zero
  accounting separately, including missing/final-usage/counter/cost/status
  negatives.
- Hermetic phase and configured-provider local plumbing phase both pass.
- Main absent-variable command reports hermetic pass, real-provider false, and
  exactly one live-qualified false line.
- Scoped Ruff/compileall, `git diff --check`, review threads, and routine CI are
  clean. No full local suite.

## Publication

Commit implementation, then publish one immutable
`oap/reports/022-e-qwen38-text-codex-qualification.md` report-only final commit
with literal implementation head and `Report publication commit: SELF` on PR
#248. Report exact focused/hermetic/plumbing results, live dynamic-accounting
negatives, absent variables, review state, and checks. Verify remote head,
signal exact response-FIFO `OK`, and return to one control wait. Never merge.
