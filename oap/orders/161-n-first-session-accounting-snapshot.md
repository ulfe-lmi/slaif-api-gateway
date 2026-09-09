# OAP Work Order — 161-n

PR mode: `AMEND_EXISTING_PR`

## Objective

Amend Objective-161 PR #298 with one verifier-only, first-session accounting
diagnostic. Reuse the corrected canonical provider env and full-image target
first turn, capture the existing safe PostgreSQL reservation/ledger/replay
snapshot after the natural two-request function/message lifecycle, and stop
before resume. Do not change the strict target expectation in this round.

Publish FAILED whether the snapshot control succeeds or fails because the
resumed image/history target remains unaccepted. This is one newly authorized
diagnostic, not a rerun of 161-m. Run no resume, alternate control, or second
process.

## Exact current state and review

- Repository/PR: `ulfe-lmi/slaif-api-gateway`, PR #298.
- Branch/base: `oap/161-codex-assistant-output-history` onto exact current
  `main` `910ddaa23763883c07f5d2065662eb1157deb9f1`.
- 161-m implementation head:
  `caa2c98f05a209b90857f774a10bcacd595cfc8e`.
- Immutable 161-m FAILED report/current PR head:
  `39adabf1f2c3c155cf0aafe99fe80b65acde1675`.
- Report:
  `oap/reports/161-m-canonical-provider-env-and-prefixed-reproduction.md`.
- Report commit is report-only with exact implementation first parent;
  implementation changed only order/active and two verifier/test paths.
- All ten implementation checks passed. Final report-head checks must all pass
  before this activation is signalled. PR #298 remains open, non-draft,
  mergeable, unique for Objective 161, without reviews/threads/auto-merge.
- Remote main/release, unrelated PRs #224/#250, historical PR #291, and frozen
  Local PR #7 remain unchanged/out of scope. Local PR #7 stays at report head
  `5aec2beccc07432d45e936b82952abf52dfb10d8`, implementation parent
  `64e50172ee02563e2b021554f6b0d345cc7dfdec`.
- Objective 161 still changes only OAP transcript, one verifier, and unit tests;
  no production/dependency/schema/CI/contract/docs path has changed.

161-m fixed the exact env mismatch: command and environment now use only
`SLAIF_CODEX_CAPTURE_API_KEY`, stale alias is denied, and provider semantic
comparison passes. A fresh full target run crossed first client and completed
the natural first session, then stopped before resume at
`accounting_before_rejection_invalid`. Exactly one run occurred; no retry or
post-run mutation.

The current verifier's safe snapshot expects two finalized reservations, two
finalized successful ledgers, zero pending/failed/released state, and
`replay_references=zero`. Product source shows validated function/custom call
candidates are persisted after accounting finalization and are used to
authenticate a natural tool-output continuation. The successful two-request
first session therefore makes nonzero replay state plausible, but the 161-m
report omitted all safe snapshot fields. Observe them before correction.

The 161-m report also failed to include the required clarification of 161-l's
contradictory no-test sentence. The 161-n report must state: 161-l ran the
required governance pytest 8/8 but no verifier/product/reproduction command.

Abort on topology/env/accounting/frozen-Local discrepancy. Never create a
replacement PR.

## Exact allowed paths

Only these may change:

- `scripts/verify_codex_0149_assistant_output_history.py`
- `tests/unit/test_codex_0149_assistant_output_history.py`
- `oap/active`
- `oap/orders/161-n-first-session-accounting-snapshot.md`
- `oap/reports/161-n-first-session-accounting-snapshot.md`

Do not change app, capture/accepted fixtures, Objective-160, Local, production
replay/accounting, DB/schema/migrations, dependencies/lockfiles, CI, contracts,
doctrine, or docs.

## Required accounting diagnostic

1. Add one explicit CLI mode `--diagnostic-accounting-before-rejection`,
   mutually exclusive with all existing controls. Default target and prior
   controls remain semantically unchanged.
2. Reuse exact default target setup through successful first client: canonical
   env, full image, validated vision catalog, same prompt/command, Gateway,
   fake Local, zero retries, and private module-mode environment.
3. After first client exits 0, require one private session, Gateway statuses
   exactly `200,200`, first request image class `full`, all later first-session
   image classes `none`, fake Local exactly two signed requests with one
   function and one message lifecycle, and no third request.
4. Query existing `_accounting_snapshot()` exactly once after that lifecycle.
   Do not apply `_accounting_snapshot_is_two_terminal_successes()` and do not
   mutate any row. Stop before constructing or invoking resume.
5. Serialize only the existing closed fields in fixed order:
   reservations total/finalized/pending/released; ledgers total/finalized/
   pending/failed/successful; replay references; query success. Values remain
   zero/one/two/other or boolean. Include Gateway/status/image/Local classes and
   cleanup booleans. No IDs, HMACs, statuses outside allowlists, amounts,
   tokens, rows, DB URLs, or content.
6. Emit one fixed diagnostic success line. On setup/first-client/query failure,
   use existing closed stage/turn/accounting diagnostics. Run no resume.
7. Preserve raw-output deletion and verify no prompt/image/body/JSONL/tool/
   identifier/secret/path value enters state, output, report, or repr.

## Tests and preflight

Starting focused collection is exactly 109 cases. Collect before edits, add
pure tests for CLI exclusivity, exact first-session branch/stop-before-resume,
fixed snapshot serialization, all count values, malformed/unknown key denial,
Gateway/full-image/Local predicates, query failure, cleanup, and raw-value
exclusion. Report exact final collection/execution, never a stale count.

Before the one diagnostic:

- run complete verifier and active governance tests;
- compile changed Python and run Ruff check/format;
- run accounting snapshot/serialization/privacy and all retained env/source/
  diagnostic/provenance/catalog/image/command/observer tests;
- run `git diff --check`, allowed-path proof, no report collision;
- push final non-report implementation head and require all ten normal checks
  successful on that exact head;
- create fresh private Python 3.12 `.[dev]`, pass pip/import/module/provenance/
  canonical-env gates.

Missing, skipped, pending, failed, stale, or blocked evidence is not a pass.
Repair only before the diagnostic. After it begins, no mutation or second run.

## One diagnostic run and boundaries

Run exactly once:

```text
env -u TEST_DATABASE_URL -u DATABASE_URL -u RUN_UPSTREAM_TESTS
  ENABLE_EMAIL_DELIVERY=false PYTHONPATH=app
  <task-python> -m scripts.verify_codex_0149_assistant_output_history
  --diagnostic-accounting-before-rejection
```

Routine private Python/npm and disposable PostgreSQL setup are authorized.
Never mutate global state or use `DATABASE_URL` destructively. No protected
credential/service, Local mutation, Qwen, real provider, hosted tool,
deployment, release, or production system. PostgreSQL remains accounting
truth.

## Immutable report

Commit unchanged 161-n order/active with verifier/tests. Run from exact clean
implementation head after ten green checks. Then publish only:

`oap/reports/161-n-first-session-accounting-snapshot.md`

Report `RESULT=FAILED`, mechanically verified implementation SHA,
`Report publication commit: SELF`, topology/diff, corrected 161-l wording,
exact test counts, preflight/checks, one first-session control, every safe
snapshot/Gateway/image/Local/cleanup field, privacy/docs/skips/deviations, and:

```text
PREFX-ACCOUNTING-SNAPSHOT-ACCEPTED = YES|NO
PREFX-PROVIDER-ENV-ACCEPTED = YES|NO
PREFX-REPRODUCTION-ACCEPTED = NO
IMPLEMENTED = NO
TESTED = NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = NO
LOCAL-CROSS-CONTRACT-ACCEPTED = NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO
```

Final commit changes only that report, has literal implementation first parent,
and is remote PR #298 head before response `OK`. Report-head checks may be
pending; strategic verifies. Coding never merges/auto-merges and returns to the
permanent control-wake helper.
