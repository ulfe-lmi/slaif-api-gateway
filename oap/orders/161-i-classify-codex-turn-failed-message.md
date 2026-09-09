# OAP Work Order — 161-i

PR mode: `AMEND_EXISTING_PR`

## Objective

Amend Objective-161 PR #298 to project the exact Codex 0.149 first-client
`turn.failed` JSONL event into bounded, source-pinned, privacy-safe facts.
Preserve the accepted private module-mode invocation, package/native
provenance, command, catalog, images, Gateway baseline, and fake Local; then
run exactly one fresh zero-retry diagnostic reproduction.

This is verifier-only evidence work. Do not implement assistant-history
acceptance or change production behavior/docs. PASSED requires the exact
full-image/resumed-crop rejection. Otherwise publish FAILED with the closed
turn-failure projection and stop. Immutable 161-h remains FAILED and must not
be rerun, amended, or relabeled.

## Verified current state and reason

- Repository/PR: `ulfe-lmi/slaif-api-gateway`, PR #298.
- Branch/base: `oap/161-codex-assistant-output-history` onto exact current
  `main` `910ddaa23763883c07f5d2065662eb1157deb9f1`.
- 161-h implementation head:
  `7630eae5f890d3a56de6b36feaee6a5c6887732e`.
- Immutable 161-h FAILED report/current PR head:
  `d3c43446986a4a1b705ce4959fcda1c175ba7cd7`.
- Report: `oap/reports/161-h-module-invocation-prefixed-reproduction.md`.
- The implementation commit changes only 161-h order/active; the report commit
  changes only its report and has the implementation head as first parent.
- All ten checks pass on both heads. PR #298 is open, non-draft,
  CLEAN/mergeable, with no reviews/threads/auto-merge, and is the unique
  Objective-161 PR.
- Remote main, release `v0.1.0-rc.1`, unrelated PRs #224/#250, historical PR
  #291, and frozen Local PR #7 are unchanged/out of scope. Local PR #7 remains
  at report head `5aec2beccc07432d45e936b82952abf52dfb10d8`, implementation
  parent `64e50172ee02563e2b021554f6b0d345cc7dfdec`.
- Objective 161 still changes only OAP transcript, this verifier, and its unit
  tests; no production/dependency/schema/CI/contract/docs path has changed.

161-h proved a fresh private Python 3.12 `.[dev]` environment, combined
imports, module resolution/`--help`, 81 verifier tests, 8 governance tests,
static checks, package/native provenance, and activation-head CI. Exactly one
module-mode run is corroborated; a later matching string was report
publication only. The run reached first client and returned:

```text
codex_first_turn_turn_failed_gateway_zero_status_none_error_other_param_other_local_zero
```

Thus Codex launched and emitted `turn.failed` before any Gateway request. No
full/crop/history/Local/accounting predicate was established, and there was no
rerun or post-run mutation.

Exact public source tag `rust-v0.149.0`, commit
`758ef40f50c1a458425c7cfbf1eb12cbc07af0b0`, proves:

- `codex-rs/exec/src/exec_events.rs` maps `turn.failed` to
  `TurnFailedEvent { error: ThreadErrorEvent }`;
- `ThreadErrorEvent` contains exactly free-text `message: String`;
- `codex-rs/exec/src/event_processor_with_jsonl_output.rs` emits the protocol
  error message for failed turns;
- current `classify_codex_failure()` scans fixed stderr markers, then retains
  only event type `turn.failed` and returns generic `turn_failed`.

The message may contain content/paths and must never be printed, stored, or
hashed into evidence. A closed transient classifier is required before any
command/catalog/product correction. Abort on any topology/source/dependency
discrepancy; never create a replacement PR.

## Exact allowed paths

Only these may change:

- `scripts/verify_codex_0149_assistant_output_history.py`
- `tests/unit/test_codex_0149_assistant_output_history.py`
- `oap/active`
- `oap/orders/161-i-classify-codex-turn-failed-message.md`
- `oap/reports/161-i-classify-codex-turn-failed-message.md`

Do not change app, accepted/capture fixtures, Objective-160 files, Local,
replay/HMAC, DB/schema/migrations, dependencies/requirements/lockfiles, CI,
contracts, doctrine, or docs.

## Required turn-failure projection

Implement one pure parser/classifier local to this verifier:

1. Pin the exact source tag/commit and the two source paths above in constants
   and tests; no runtime source/network access.
2. Inspect at most 512000 stdout bytes, 256000 stderr bytes, 64 JSONL records,
   65536 bytes per line, and one 65536-byte UTF-8 message. Over-limit data
   becomes only fixed `oversized`/`truncated` classes.
3. Parse only top-level objects. Allowlist exact event classes
   `thread.started`, `turn.started`, `turn.failed`, `turn.completed`,
   `item.started`, `item.updated`, `item.completed`, and `error`; collapse all
   others to `other`. Retain at most eight ordered classes and bounded counts.
4. Require exactly one diagnostic `turn.failed`. Record only exactness of
   top-level fields `type,error`, exactness of nested `message`, type, and
   empty/bounded/invalid/oversized class. Duplicate/malformed/extra shapes get
   fixed classes.
5. Classify valid bounded message transiently into exactly one closed domain:
   `invalid_image`, `image_processing_or_capability`,
   `model_catalog_or_model`, `configuration`, `authentication`,
   `workspace_or_sandbox`, `request_or_transport`, `stream_or_response`,
   `internal_runtime`, exact generic `turn failed`, or `other`. Use fixed
   lowercase ASCII markers/conjunctions only; emit no matched text.
6. Combine with the existing fixed stderr classifier and record only
   stderr-specific, message-specific, agreeing, conflicting, or generic class.
7. Delete raw stdout/stderr/parsed references immediately after projection.
   Never retain message/line text, arbitrary event names, hashes, paths, IDs,
   prefixes/suffixes, exception details, or subprocess output.
8. For first-client nonzero exit, replace only generic `turn_failed` in the
   known verifier code with closed shape/domain/event/count classes plus the
   existing Gateway/Local progress. Preserve specific stderr and all other
   existing codes.
9. Do not alter command, prompt, image, catalog, provider profile, environment,
   timeout/retry, observer, fake Local, or success/rejection predicates.

## Tests and preflight

Add pure tests for all domains; exact source pins/field relationship;
malformed/non-object/missing/duplicate/extra/wrong-type/empty cases; all byte,
line, record, event, and message bounds; allowlist/order/count behavior;
stderr-only/message-only/agreement/conflict/generic results; and raw canary
exclusion from result, `str`, `repr`, and serialized facts. Preserve all 81
existing tests and all diagnostic/provenance/catalog/image/command/observer/
accounting/privacy negatives.

Before the one run:

- run complete verifier and active-governance tests;
- compile changed Python and run Ruff check/format;
- run source-bound classifier/privacy and all retained focused tests;
- run `git diff --check`, exact allowed-path proof, no report collision;
- push final non-report implementation head and require all ten normal checks
  successful on that exact head;
- create a fresh private Python 3.12 `.[dev]` environment and pass `pip check`,
  combined imports, module resolution/`--help`, and exact package/native
  provenance as in 161-h.

Skipped, xfailed, missing, cancelled, pending, neutral, stale-head, or blocked
evidence is not a pass. Repairs are allowed only before the run. After the run
begins, no mutation or second run is authorized.

## One diagnostic reproduction

Run exactly once from the clean implementation head with zero retries:

```text
env -u TEST_DATABASE_URL -u DATABASE_URL -u RUN_UPSTREAM_TESTS
  ENABLE_EMAIL_DELIVERY=false PYTHONPATH=app
  <task-python> -m scripts.verify_codex_0149_assistant_output_history
```

PASSED requires exact statuses `200,200,400`, full then crop image classes,
prior assistant `output_text` with exact fields/bounded Unicode, rejection
`responses_input_content_part_not_supported` at
`input[5].content[0].type`, fake Local two signed requests with one function
and message lifecycle, zero rejected-turn reservation/ledger/replay side
effects, zero retries, and cleanup.

If first client still fails pre-Gateway, FAILED must include only the closed
turn-failure shape/domain/event/stderr/progress classes. Other failures use the
existing 161-f diagnostic. No second run or same-round correction.

## Boundaries, setup, and publication

Routine private Python/npm and disposable PostgreSQL setup are authorized.
Never mutate global state, use `DATABASE_URL` destructively, install system
packages, access production data, or retain task environments. No protected
credential/service, Local mutation, Qwen, real provider, hosted tool,
deployment, cutover, release, or production system is authorized. PostgreSQL
remains accounting truth.

No prompt/completion/reasoning/media/body/raw JSONL/message/tool payload/raw ID/
secret/signature/endpoint/DB URL/private path/environment/package output/
traceback/hash of diagnostic text/arbitrary error may be logged, committed, or
reported. Docs need no update because behavior is unchanged.

Commit the unchanged 161-i order/active with verifier/tests to the same PR.
Run only from the exact clean implementation head after its ten checks pass.
Then publish exactly one immutable report and no other mutation:

`oap/reports/161-i-classify-codex-turn-failed-message.md`

The report contains `RESULT=PASSED|FAILED`, literal implementation SHA,
`Report publication commit: SELF`, topology/diff, source/classifier tests,
preflight/checks, exact one-run result, closed projection or target predicates,
privacy/accounting/cleanup/docs/skips/deviations, and:

```text
PREFX-TURN-FAILURE-DIAGNOSTIC-ACCEPTED = YES|NO
PREFX-ENVIRONMENT-ACCEPTED = YES|NO
PREFX-MODULE-INVOCATION-ACCEPTED = YES|NO
PREFX-PROVENANCE-ACCEPTED = YES|NO
PREFX-REPRODUCTION-ACCEPTED = YES|NO
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
