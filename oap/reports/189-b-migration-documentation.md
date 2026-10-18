# OAP Execution Report — Objective 189-b: migration documentation corrections

Report status: IMMUTABLE (finalized at the exact implementation head
`07ec417865a948de85d4418406c017f55ba0fd8b`; published atomically as the
immutable report; the report-only SELF commit with message
`Report publication commit: SELF` is its publication commit, first
parent = this implementation head; only this report path differs).

- Implementation head SHA: 07ec417865a948de85d4418406c017f55ba0fd8b
- Report publication commit: SELF

## 1. Work order and PR identity

- Work order: `oap/orders/189-b-migration-documentation.md`
  (strategic-authored; committed unchanged by the activation commit
  `876663cba5641400f7c12f72e038f36a5b8a2711`); `oap/active` = `189-b`.
- PR mode: AMEND_EXISTING_PR — the same unique PR #327
  `fix: accept bounded Codex additional-tools identifiers and register the
  0.162.1 profile` on branch `oap/189-codex-additional-tools-id` (base
  `main` at `0380f62d2bf7b57e831143801ef5532165eaddeb`, unchanged). No
  second PR. The PR body already carries the qualification evidence and
  was not modified; no new runs are claimed.
- Predecessor: 189-a report-only SELF
  `d3bee58238bc2221d24bc9901d62499e7ecbd61c` (implementation
  `73fd10567a6c2558f4ec233a90ba3818745bacca`) remains immutable history.

## 2. Scope (two prose corrections only)

1. `docs/upgrade-runbook.md` — the sentence claiming repeated moves fail
   closed was replaced with the exact behavior: only the four listed
   transitions are supported; an exact repeat of an already-at-target key
   (dry run or `--apply`) is a successful no-op that performs no
   additional audit mutation; drifted or unexpected module identities and
   cross-target moves fail closed. The dry-run/apply/rollback commands and
   all other operational advice are preserved.
2. `docs/verification/codex-0162-local-tools.md` — the statement that
   "policy/admission run first" was corrected to the accurate pipeline
   timing: request-policy validation/canonicalization precedes the pure
   lowering; the original validated declaration remains the estimation
   input; pure body construction may precede quota reservation in the
   existing pipeline; actual forwarding requires successful admission; the
   final HMAC covers the final bytes; both the initial and the refreshed
   after-wait body builds remain covered; no claim that any accounting
   step was moved.

No product-code, test, fixture, schema, dependency, config, workflow, UI,
or other-repository change. No runtime, unit, PG, E2E, browser, or matrix
reruns were performed for these prose changes.

## 3. Bounded-diff verification (explicit)

`git diff --name-only d3bee58238bc2221d24bc9901d62499e7ecbd61c
07ec417865a948de85d4418406c017f55ba0fd8b` lists exactly:

- `docs/upgrade-runbook.md`
- `docs/verification/codex-0162-local-tools.md`
- `oap/active`
- `oap/orders/189-b-migration-documentation.md`

Product code, tests, fixtures, source digests, and every earlier immutable
OAP byte (orders, strategic instructions, the 189-a report, and the
activation/scope/lowering decision commits) are unchanged.
`git diff --check` is clean.

## 4. Carried-forward evidence (no new runs)

Evidence from the predecessor 189-a implementation is preserved as
recorded there: independent 503 distinct unit cases; 14 real-PostgreSQL
integration cases; 3 synthetic-197 Gateway/mock-backend E2E cases; 2
legacy 0.149 Local E2E cases (independent rerun, 0 skips); and the actual
official 0.162.1 CLI → real Gateway/owned PG/signed Local → loopback mock
backend success. No real model, private plugin, or deployed-fix claim is
carried. The deployed baseline remains as recorded until keys are migrated
on a deployed build.

## 5. Pending and honest limitations

- Final-head CI on this new head is PENDING and is not a pass; the
  predecessor head's checks do not transfer to this commit. Strategic
  waits for all final-head checks, guards the merge, verifies actual
  `main` checks, and records timings.
- No acceptance, approval, or merge follows from this report; the agent
  never merges or enables auto-merge.
