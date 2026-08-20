# OAP Work Order — 015-d

## Objective

Amend PR #240 with final direct evidence that reconciliation controls ordinary
following requests, not only later external-fence acquisition, and that a
changed-input race leaves one exact durable outcome. This is tests-only unless
the direct proof exposes a concrete defect.

## Current state

- Remote `main`: `ef3fdb8ce37381327ebf784b141ab9f7d5f75729`.
- Sole objective PR: #240 on
  `oap/015-external-tool-accounting-hold-reconciliation`.
- Current report head:
  `6763f80e7a8c954048e5fb131ededa7109b04a0d`.
- Its 015-c implementation parent:
  `ee39226315d6c33313b682ad9d1406e84f74da3c`.
- All ten current report-head checks are successful.
- 015-c's within-limit, overrun, and no-charge tests attempt
  `ExternalToolFenceService.acquire`; they do not call ordinary `QuotaService`
  even though the product promise covers following ordinary requests.
- Its changed-input two-worker test checks one winner/one conflict but does not
  inspect final counters, ledger, reservation, fence, or audit despite the
  report claiming no second mutation/audit.

Prior OAP artifacts are immutable. Reconcile once, edit the two hold
PostgreSQL files immediately, and do no general reconnaissance.

## Required direct evidence

Construct a normal `AuthenticatedGatewayKey`, `RouteResolutionResult`, bounded
ordinary policy, and cost estimate, then call
`QuotaService.reserve_for_chat_completion` after:

1. `release-no-charge`: a fitting ordinary reservation succeeds;
2. within-limit actual finalization: a fitting ordinary reservation succeeds;
3. cost/token overrun finalization: ordinary reservation fails through the
   normal quota-limit error and creates no reservation/counter mutation.

Also place a real hold and prove both bearer authentication and an ordinary
pre-authenticated quota reservation reject the held key. This joins the 015
transition to the 014 defensive checks in one PostgreSQL scenario.

For the changed-input two-worker reconciliation race, inspect final state:

- exactly one terminal reservation and one ledger;
- fence none only after winning terminal evidence;
- used/reserved counters equal the winner once;
- exactly one `external_tool_accounting_hold_reconciled` audit with winning
  actor/reason/numeric facts;
- loser conflict causes no second audit/mutation;
- bounded timeout/no deadlock remains.

Keep the existing external-fence follow-up assertions; ordinary quota proof is
additional.

## Allowed paths

```text
oap/active
oap/orders/015-d-prove-following-ordinary-admission-and-race-state.md
tests/integration/test_external_tool_hold_concurrency_postgres.py
tests/integration/test_external_tool_hold_postgres.py
```

If a direct test proves a production defect, do not edit outside scope; report
the blocker for a narrow continuation. Final report-only commit adds:

```text
oap/reports/015-d-prove-following-ordinary-admission-and-race-state.md
```

## Verification

Run only the two hold PostgreSQL files against one safe disposable
`TEST_DATABASE_URL`, no skips, plus scoped Ruff/compile/diff/path checks and
final GitHub CI. No full local suite, provider, email, Redis authority,
production, schema, migration, docs, or runtime changes.

## Acceptance criteria

1. Held blocks real auth and ordinary quota after actual hold transition.
2. No-charge and within-limit reconciliation permit a fitting ordinary request.
3. Overrun reconciliation rejects a following ordinary request through normal
   quota limits with zero new mutation.
4. Changed-input race has one exact durable winner and one zero-effect conflict.
5. Same PR #240, all focused/final checks green, no merge/auto-merge, exact
   report `SELF` topology.

## GitHub/report contract

Commit unchanged order and `oap/active=015-d`, push to PR #240 only, never
merge. Publish one immutable
`oap/reports/015-d-prove-following-ordinary-admission-and-race-state.md` with
literal implementation SHA, `Report publication commit: SELF`, exact ordinary
admission/error/counter/reservation outcomes, race winner/loser/audit facts,
commands/counts/cleanup/privacy/no-provider/no-broad-suite/no-merge evidence.
Report commit parents implementation and changes only itself; verify, signal
`OK`, return to control FIFO.
