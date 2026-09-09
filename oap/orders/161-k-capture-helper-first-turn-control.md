# OAP Work Order — 161-k

PR mode: `AMEND_EXISTING_PR`

## Objective

Amend Objective-161 PR #298 with one verifier-only no-image first-turn control
built by the exact pinned `capture._exec_command_0149()` helper used by the
network-reaching 161-a verifier. Hold interpreter, package, model catalog,
provider, prompt, Gateway, fake Local, and no-image condition fixed; isolate
the manually rewritten `_initial_command()` argv aliases/order.

Do not change production/docs or implement assistant-history acceptance. This
is one newly authorized altered-command control, not a rerun of 161-j. Publish
FAILED after the control whether it succeeds or fails because the target image
and history reproduction remains unaccepted. No second control or image run.

## Verified current state and review findings

- Repository/PR: `ulfe-lmi/slaif-api-gateway`, PR #298.
- Branch/base: `oap/161-codex-assistant-output-history` onto exact current
  `main` `910ddaa23763883c07f5d2065662eb1157deb9f1`.
- 161-j implementation head:
  `c7b50cede420f1d938b29de69e44eb9928641eba`.
- Immutable 161-j FAILED report/current PR head:
  `592da3ec907b54ba48f0523fed31a9dac9c1dd91`.
- Report: `oap/reports/161-j-no-image-first-turn-control.md`.
- Report-only topology and implementation first parent are correct;
  implementation changed only order/active and two verifier/test paths.
- All ten checks pass on implementation and report heads. PR #298 is open,
  non-draft, CLEAN/mergeable, has no reviews/threads/auto-merge, and is the
  unique Objective-161 PR.
- Final-head `Unit, lint, and migration head` passed 3874 tests with 1 skip.
- Remote main, release `v0.1.0-rc.1`, unrelated PRs #224/#250, historical PR
  #291, and frozen Local PR #7 are unchanged/out of scope. Local PR #7 remains
  at report head `5aec2beccc07432d45e936b82952abf52dfb10d8`, implementation
  parent `64e50172ee02563e2b021554f6b0d345cc7dfdec`.
- Objective 161 still changes only OAP transcript, one verifier, and its unit
  tests; no production/dependency/schema/CI/contract/docs path has changed.

161-j added one ordinary and one four-case parameterized pure test: five new
collected cases. Since 161-i reported 102 tests and no test was removed, exact
161-j final-head focused collection is 107. The immutable 161-j report instead
repeats `102`; this is a report-accuracy defect. Do not edit that report.
Require machine collection and execution of exactly 107 current tests before
adding 161-k tests, then report the new exact collection after additions.

161-j ran exactly one no-image current-command control. It failed with the same exact
`turn.failed` shape/domain/relation and zero Gateway/Local progress as the image
run. Therefore image attachment is not the cause. The shared boundary is first-
turn command/provider/model setup.

Immutable 161-a reached Gateway statuses `200,200,400` using the exact
`capture._exec_command_0149()` first command before its image insertion.
Current `_initial_command()` is a manual reconstruction. Its intended semantic
facts match but aliases/order differ, including helper `-C`/`-o` placement
versus manual `--cd`/`--output-last-message`. A one-variable helper-command
control is required before changing catalog/provider/environment.

Abort on any topology, count, provenance, helper-source, or frozen-Local
discrepancy. Never create another PR.

## Exact allowed paths

Only these may change:

- `scripts/verify_codex_0149_assistant_output_history.py`
- `tests/unit/test_codex_0149_assistant_output_history.py`
- `oap/active`
- `oap/orders/161-k-capture-helper-first-turn-control.md`
- `oap/reports/161-k-capture-helper-first-turn-control.md`

Do not change app, accepted/capture helper/fixtures, Objective-160 files,
Local, replay/HMAC, DB/schema/migrations, dependencies/requirements/lockfiles,
CI, contracts, doctrine, or docs.

## Required helper-command control

1. Add one explicit CLI mode
   `--diagnostic-capture-helper-no-image-first-turn`, mutually exclusive with
   `--diagnostic-no-image-first-turn`. Default target mode remains unchanged.
2. Build the control by calling the existing pinned
   `capture._exec_command_0149()` with the exact current binary, workdir, port,
   model, current validated catalog, output path, `ephemeral=False`, and the
   byte-identical current first-turn prompt. Do not copy/reimplement the helper.
3. Do not insert an image. Require no `--image`, full/crop path, resume, second
   output, alternate prompt, hosted tool, or extra config.
4. Compare the helper control to the 161-j no-image command through a bounded
   semantic projection. Require identical executable, yolo/exec/json/strict/
   ignore-user-config flags, workdir, model, provider name/base/env/wire,
   model-catalog path, update setting, request/stream retries, output path, and
   prompt. Allow only the exact reviewed alias/order differences produced by
   the helper; reject any semantic difference or raw-path retention.
5. Reuse the accepted private Python 3.12 module-mode environment, package/
   native provenance, DB/key/route, catalog, Gateway observer, and signed fake
   Local. Run only the first session and never build/invoke resume.
6. Control success requires Codex exit 0, one private session, Gateway statuses
   `200,200`, fake Local exactly two signed requests with one function and one
   message lifecycle, zero image parts/classes in every request, no third
   request, and exact terminal PostgreSQL state for two admitted requests with
   zero pending reservation/replay state.
7. Emit one fixed helper-control result using only aliases/order equality,
   Gateway/Local/image/accounting count classes and cleanup booleans. On
   failure use existing closed stage/turn-failure progress.
8. Preserve default target and 161-j modes byte-semantically. Do not alter
   command helper, catalog, prompt, environment, timeout, retries, fake Local,
   Gateway, or production code.

## Tests and preflight

First collect the 161-j starting test file and require exactly 107 cases.
Add pure tests for CLI exclusivity; exact helper construction; bounded semantic
equivalence and allowed aliases/order; no-image/no-resume containment; wrong
model/provider/catalog/retry/output/prompt rejection; helper success/failure
and accounting predicates; unchanged default/161-j modes; and raw content/path/
ID/secret/DB-value exclusion. Report exact final collection and execution
counts; never reuse a stale count.

Before the one control:

- run complete verifier and active governance tests;
- compile changed Python and run Ruff check/format;
- run exact command differential/accounting/privacy tests and all retained
  diagnostics/provenance/catalog/image/observer negatives;
- run `git diff --check`, exact allowed-path proof, no report collision;
- push final non-report implementation head and require all ten normal checks
  successful on that exact head;
- create a fresh private Python 3.12 `.[dev]` environment and pass `pip check`,
  combined imports, module resolution/`--help`, and package/native provenance.

Skipped, xfailed, missing, cancelled, pending, stale, or blocked evidence is
not a pass. Repair in-scope verifier/tests only before the control. After it
begins, no mutation, alternate control, image run, or second process.

## One exact control and boundaries

Run exactly once from the clean implementation head:

```text
env -u TEST_DATABASE_URL -u DATABASE_URL -u RUN_UPSTREAM_TESTS
  ENABLE_EMAIL_DELIVERY=false PYTHONPATH=app
  <task-python> -m scripts.verify_codex_0149_assistant_output_history
  --diagnostic-capture-helper-no-image-first-turn
```

Routine private Python/npm and disposable PostgreSQL setup are authorized.
Never mutate global state or use `DATABASE_URL` destructively. No protected
credential/service, Local mutation, Qwen, real provider, hosted tool,
deployment, release, or production system is authorized. PostgreSQL remains
accounting truth.

Never retain/report prompts, completions, reasoning, media, bodies/JSONL,
turn-failure text, tool payloads, IDs, secrets, endpoints, DB URLs, private
paths, environment/package output, tracebacks, or diagnostic hashes. Docs need
no update because this is verifier-only evidence.

## Immutable report and stop law

Commit unchanged 161-k order/active with verifier/tests to the same PR. Run
only from its exact clean implementation head after ten green checks. Publish
exactly one immutable report afterward:

`oap/reports/161-k-capture-helper-first-turn-control.md`

The report contains `RESULT=FAILED`, implementation SHA, `Report publication
commit: SELF`, topology/diff, corrected starting/final test counts, preflight/
checks, exactly-one-control result, command-semantic/Gateway/Local/image/
accounting or closed failure evidence, privacy/cleanup/docs/skips/deviations,
and:

```text
PREFX-CAPTURE-HELPER-CONTROL-ACCEPTED = YES|NO
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

Final commit changes only that report, has implementation first parent, and is
remote PR #298 head before response `OK`. Report-head checks may be pending;
strategic verifies them. Coding never merges/auto-merges and returns to the
permanent control-wake helper.
