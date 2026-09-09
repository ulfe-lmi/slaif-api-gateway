# OAP Work Order — 161-j

PR mode: `AMEND_EXISTING_PR`

## Objective

Amend Objective-161 PR #298 with one verifier-only first-turn control that is
identical to the accepted 161-i setup and command except that it removes the
single `--image <full-fixture>` argv pair and stops before resume. Determine
whether Codex 0.149 reaches the unchanged Gateway/fake-Local two-request first
session without image attachment.

Do not implement assistant-history acceptance or change production/docs. This
is not a retry of 161-i: it is one newly authorized altered-condition control.
Publish FAILED after the control, whether it succeeds or fails, because the
target image/history reproduction remains unaccepted. Record the exact
closed control result and stop; do not run the image case again in this round.

## Verified current state and hypothesis

- Repository/PR: `ulfe-lmi/slaif-api-gateway`, PR #298.
- Branch/base: `oap/161-codex-assistant-output-history` onto exact current
  `main` `910ddaa23763883c07f5d2065662eb1157deb9f1`.
- 161-i implementation head:
  `e99ab6573a66571cad10b761e6f5d3c8d1373b5a`.
- Immutable 161-i FAILED report/current PR head:
  `fed0834332ad2aee305617350f73afb8057fc124`.
- Report: `oap/reports/161-i-classify-codex-turn-failed-message.md`.
- Report commit is report-only with implementation first parent; implementation
  changed only its order/active and two verifier/test paths.
- All ten checks pass on implementation and report heads. PR #298 is open,
  non-draft, CLEAN/mergeable, has no reviews/threads/auto-merge, and is the
  unique Objective-161 PR.
- Remote main, release `v0.1.0-rc.1`, unrelated PRs #224/#250, historical PR
  #291, and frozen Local PR #7 are unchanged/out of scope. Local PR #7 remains
  at report head `5aec2beccc07432d45e936b82952abf52dfb10d8`, implementation
  parent `64e50172ee02563e2b021554f6b0d345cc7dfdec`.
- Objective 161 still changes only OAP transcript, one verifier, and its unit
  tests; no production/dependency/schema/CI/contract/docs path has changed.

161-i added 21 pure tests and an exact source-bound `turn.failed` projection.
Its single module-mode run produced one exact-shaped `turn.failed` with bounded
message domain `other`, generic stderr/message relation, and zero Gateway and
Local requests. No raw message, JSONL, path, ID, or diagnostic hash survived.

The accepted private Python environment, module invocation, package/native
provenance, catalog facts, valid Local-005-q RGB fixtures, command binding,
zero retries, and CI are no longer unresolved. The first request still fails
inside Codex before HTTP only when attempting the current full-image turn.
Because the closed message provides no source-reviewed domain, a one-variable
control is required before changing catalog, image bytes, prompt, or command
topology.

Fixed hypothesis: if the exact same first session succeeds after removing only
the image argv pair, the remaining boundary is Codex local image attachment/
preparation or its interaction with selected-model metadata. If it fails in the
same pre-Gateway class, the boundary is shared first-turn command/provider/
model setup rather than image attachment. This control does not choose a fix.

Abort on any topology/provenance/fixture/frozen-Local discrepancy. Never create
a replacement PR.

## Exact allowed paths

Only these may change:

- `scripts/verify_codex_0149_assistant_output_history.py`
- `tests/unit/test_codex_0149_assistant_output_history.py`
- `oap/active`
- `oap/orders/161-j-no-image-first-turn-control.md`
- `oap/reports/161-j-no-image-first-turn-control.md`

Do not change app, accepted/capture fixtures, Objective-160 files, Local,
replay/HMAC, DB/schema/migrations, dependencies/requirements/lockfiles, CI,
contracts, doctrine, or docs.

## Required no-image control

1. Add exactly one explicit verifier CLI mode named
   `--diagnostic-no-image-first-turn`. Default invocation must remain the
   unchanged full target reproduction; reject unknown or conflicting args.
2. Derive the control argv from `_initial_command()` and remove exactly one
   adjacent `--image` plus full-fixture path pair. Require the baseline command
   has exactly that one pair before removal. Every other argv value, order,
   prompt, model/provider/catalog config, workdir, output binding, retry value,
   and executable must be byte-identical.
3. Validate the control command contains no `--image`, full/crop path, resume,
   second output, alternate prompt, hosted tool, or extra config. Do not alter
   the catalog's exact vision facts; this isolates attachment from metadata.
4. Reuse the exact private module-mode Python setup, Codex package/native
   attestation, generated DB/key/route, Gateway observer, and signed fake Local.
5. Run only the first Codex session. The fake Local's deterministic lifecycle
   may generate at most two Gateway requests: initial function call and natural
   tool-output continuation to assistant message. Never build or invoke resume.
6. A successful no-image control requires Codex exit 0; one private session;
   Gateway statuses exactly `200,200`; fake Local exactly two signed requests,
   one function and one message lifecycle; every observed request image count
   `zero`; no full/crop/other image class; and no third request.
7. Query PostgreSQL after the first session using existing schema/models and
   safe metadata only. Require zero pending reservations/replay writes and the
   exact terminal ledger/reservation relationship for the two admitted public
   requests. Do not store/report content, IDs, costs, or DB paths. If exact
   ledger cardinality cannot be proven from current behavior, report it as a
   bounded failed predicate; do not invent or change accounting.
8. Emit only one fixed control success line with Gateway/Local/image/accounting
   count classes. On failure, use the accepted 161-f/161-i closed stage,
   turn-failure, Gateway/Local, and cleanup evidence.
9. Delete subprocess output and all raw state after projection. Preserve all
   default target predicates and do not make the no-image mode an acceptance
   path for production compatibility.

## Tests and preflight

Add pure tests proving: exact one-pair removal; missing/duplicate/misplaced/
wrong-image rejection; all non-image argv byte identity; no resume; default
mode unchanged; CLI exclusivity; successful two-request zero-image control;
first-client failure projection; overrun/third-request rejection; PostgreSQL
terminal-count and pending-state predicates; and raw content/path/ID/secret/
DB-value exclusion. Preserve all 102 existing verifier tests and all source,
diagnostic, provenance, catalog, image, command, observer, accounting, and
privacy negatives.

Before the control:

- run complete verifier and active governance tests;
- compile changed Python and run Ruff check/format;
- run exact command-differential/control/accounting/privacy tests;
- run `git diff --check`, exact allowed-path proof, no report collision;
- push final non-report implementation head and require all ten normal checks
  successful on that exact head;
- create a fresh private Python 3.12 `.[dev]` environment and pass `pip check`,
  combined imports, module resolution/`--help`, package/native provenance, and
  all retained preflight gates.

Skipped, xfailed, missing, cancelled, pending, neutral, stale-head, or blocked
evidence is not a pass. Repair in-scope verifier/tests only before the control.
After it begins, no mutation, alternate control, image run, or second process is
authorized.

## One exact control run

Run exactly once from the clean implementation head:

```text
env -u TEST_DATABASE_URL -u DATABASE_URL -u RUN_UPSTREAM_TESTS
  ENABLE_EMAIL_DELIVERY=false PYTHONPATH=app
  <task-python> -m scripts.verify_codex_0149_assistant_output_history
  --diagnostic-no-image-first-turn
```

No protected credential/service, Local mutation, Qwen, real provider, hosted
tool, deployment, cutover, release, or production system is authorized.
Routine private Python/npm and disposable PostgreSQL setup are authorized;
never mutate global state or use `DATABASE_URL` destructively. PostgreSQL
remains accounting truth.

Never log/retain/report prompts, completions, reasoning, media, body/JSONL,
turn-failure text, tool payloads, raw IDs, secrets, signatures, endpoints, DB
URLs, private paths, environment/package output, tracebacks, or hashes of raw
diagnostics. Docs need no update because this is verifier-only evidence.

## Immutable report and stop law

Commit the unchanged 161-j order/active with verifier/tests to the same PR.
Run only from its exact clean implementation head after ten green checks. Then
publish exactly one immutable report and no other mutation:

`oap/reports/161-j-no-image-first-turn-control.md`

The report contains `RESULT=FAILED`, literal implementation SHA,
`Report publication commit: SELF`, topology/diff, tests/preflight/checks,
exactly-one-control evidence, zero-image/Gateway/Local/accounting result or
closed failure, privacy/cleanup/docs/skips/deviations, and:

```text
PREFX-NO-IMAGE-CONTROL-ACCEPTED = YES|NO
PREFX-TURN-FAILURE-DIAGNOSTIC-ACCEPTED = YES|NO
PREFX-ENVIRONMENT-ACCEPTED = YES|NO
PREFX-PROVENANCE-ACCEPTED = YES|NO
PREFX-REPRODUCTION-ACCEPTED = NO
IMPLEMENTED = NO
TESTED = NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = NO
LOCAL-CROSS-CONTRACT-ACCEPTED = NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO
```

The final commit changes only that report, has the implementation head as first
parent, and is remote PR #298 head before response `OK`. Report-head checks may
be pending then; strategic verifies them. Coding never merges/auto-merges and
returns to the permanent control-wake helper.
