# OAP Work Order — 161-f

PR mode: `AMEND_EXISTING_PR`

## Objective

Amend Gateway Objective-161 PR #298 to replace the verifier's terminal
`unexpected_other` collapse with a bounded, privacy-safe stage/category/
progress diagnostic that survives failure and cleanup. Preserve the accepted
Codex 0.149 package/native provenance, exact vision catalog, image fixtures,
commands, fake-Local behavior, Gateway baseline, and all prior negatives; then
run exactly one fresh zero-retry diagnostic reproduction.

This is verifier-only localization. Do not modify production code or
documentation, do not implement assistant `output_text` history acceptance,
and do not guess which foreign operation failed. If the run reaches the exact
pre-fix `200,200,400` full-image/crop/history rejection, publish PASSED. If it
fails, publish FAILED with one exact closed stage/category/progress snapshot and
stop. Immutable 161-e remains FAILED and must not be rerun or amended.

## Exact current state and reason

- Repository: `ulfe-lmi/slaif-api-gateway`.
- Round: `161-f`; amend existing PR #298. Never create another PR.
- PR/branch: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/298`,
  `oap/161-codex-assistant-output-history`.
- Base and current remote `main`:
  `910ddaa23763883c07f5d2065662eb1157deb9f1`.
- 161-e starting report head:
  `b26a016a2b753ce5a33d6bafaeec344b32c5060b`.
- 161-e implementation head:
  `2d67a2c8d5cd5c0c5831fb45a09cac4c9522bc4b`.
- Immutable 161-e FAILED report/current PR head:
  `9fb52d4a045d7374bef003df1b733087db96f032`.
- Report path:
  `oap/reports/161-e-exact-native-size-and-prefixed-reproduction.md`.
- The report commit changes only that report and has the implementation head
  as first parent. The implementation commit changed only its order/active
  pointer and two verifier/test paths.
- All ten normal checks are successful on both the 161-e implementation head
  and current report head. PR #298 is open, non-draft, CLEAN/mergeable, with no
  reviews, review threads, or auto-merge, and remains the only Objective-161
  PR.
- Current Objective-161 diff contains only immutable OAP transcript files, the
  one verifier, and its unit-test file. No production or documentation path has
  changed.
- Remote `main`, release `v0.1.0-rc.1`, unrelated PRs #224/#250, historical
  PR #291, and frozen Local PR #7 remain unchanged and out of scope. Local PR
  #7 remains at report head
  `5aec2beccc07432d45e936b82952abf52dfb10d8`, implementation parent
  `64e50172ee02563e2b021554f6b0d345cc7dfdec`.

161-e correctly replaced the impossible 128 MiB guess with exact native size
`258322048` bytes before hashing/invocation. Sixty-one verifier tests, eight
governance tests, focused static checks, exact package preflight, both exact
version probes, and all ten implementation-head checks passed. The package
manifests, npm integrities, launcher/native paths, sizes, digests, Linux-x64
source mapping, and `.bin/codex` entrypoint are accepted for this objective.

Exactly one 161-e zero-retry reproduction was launched from clean
implementation head `2d67a2c8...`; coding-session command metadata
corroborates one matching launch and no second matching launch. It terminated
with only:

```text
VERIFY_CODEX_0149_ASSISTANT_HISTORY_BASE_FAILED code=unexpected_other
```

No accepted Gateway progression, image classes, assistant-history rejection,
Local count, or no-side-effect predicate was established. No production or
protected traffic occurred and no mutation followed the run.

Source review proves the evidence gap without identifying the underlying
operation: `run_prefixed_reproduction()` invokes imported capture, database,
configuration, app/server, filesystem, process, accounting, and cleanup
operations, while `main()` maps every unhandled exception whose exact class
name is not one of five built-ins to the same `unexpected_other`. The current
top-level catch retains neither the last safe stage nor Gateway/Local progress,
and cleanup can obscure a primary failure. It is therefore unsafe to infer a
catalog, database, Gateway, client, or cleanup defect from 161-e.

Abort and report any discrepancy in PR/base/head/report topology, exact
provenance constants, frozen Local authority, or unique-order state. Never
create a replacement PR.

## Exact allowed paths

Only these paths may change:

- `scripts/verify_codex_0149_assistant_output_history.py`
- `tests/unit/test_codex_0149_assistant_output_history.py`
- `oap/active`
- `oap/orders/161-f-localize-unexpected-reproduction-failure.md`
- `oap/reports/161-f-localize-unexpected-reproduction-failure.md`

Do not change any app, accepted fixture, Objective-160 verifier/test, Local
module, replay/HMAC, database/schema/migration, dependency/lockfile, CI,
doctrine, contract, or documentation path.

## Required bounded diagnostic

Add one verifier-owned diagnostic state passed through the reproduction. It
must contain only closed enums, bounded counts/classes, and booleans; no raw
exception, request, content, identity, path, or environment value.

1. Define an exact closed stage vocabulary covering, at minimum:
   `imports`, `database_setup`, `local_start`, `fixture_setup`, `migration`,
   `seed`, `codex_install`, `catalog_generate`, `catalog_validate`,
   `app_create`, `command_build`, `gateway_start`, `first_client`,
   `session_validate`, `resume_client`, `postconditions`,
   `accounting_validate`, `cleanup`, and `complete`.
2. Advance the stage immediately before each corresponding operation. Reject
   unknown/non-enum stage mutation. Do not derive stage names from exception
   text, paths, third-party values, or runtime class names.
3. Maintain a safe snapshot with at most: current/primary stage, Gateway
   request-count class, up to four status classes, last closed Gateway error
   code and parameter class, fake-Local request/signed/function/message count
   classes, whether observer/local were initialized, whether primary failure
   existed, and cleanup success/failure booleans. Counts must use the existing
   bounded zero/one/two/other vocabulary.
4. Before every assertion or foreign call that can terminate a stage, update
   the snapshot from already-available observer/Local state. Never retain raw
   request projections, text, media, IDs, bodies, headers, signatures, URLs,
   database identifiers, paths, or exception objects in the snapshot.
5. Map unexpected exceptions into a small source-reviewed category vocabulary,
   such as capture, database/configuration, filesystem, subprocess/timeout,
   server/runtime, assertion, cleanup, or `other`. Match explicit known classes
   or fixed class/MRO names internally, but emit only the closed category.
   Never emit arbitrary type names, messages, `repr`, traceback, args, causes,
   contexts, paths, subprocess output, or unknown values.
6. Preserve every existing `VerificationError` code unchanged. For a truly
   unexpected exception, emit one deterministic fixed result containing only
   `unexpected_<stage>_<category>` plus the safe progress snapshot.
7. Cleanup must not replace or erase a primary failure. Preserve the primary
   stage/category and attach only a cleanup success/failure boolean. If cleanup
   alone fails after otherwise successful assertions, classify it at the
   closed cleanup stage and fail; never report success with failed cleanup.
8. Do not catch or normalize `KeyboardInterrupt`, `SystemExit`, or other
   control-flow `BaseException` subclasses as test evidence.
9. Keep the normal success line and all 161-e reproduction predicates exactly
   unchanged. The diagnostic grants no production behavior, retry, or broader
   error acceptance.

## Required tests and preflight

Add pure tests that do not invoke npm, Codex, PostgreSQL, or network and prove:

- exact stage vocabulary, valid transitions, unknown-stage rejection, and
  deterministic serialization;
- each closed exception category and an unknown category;
- synthetic unexpected failures before observer creation, after observer/local
  creation, during first/resume client stages, postconditions/accounting, and
  cleanup;
- primary failure survives a later cleanup failure;
- cleanup-only failure cannot produce success;
- snapshot count/status/error/parameter fields are bounded and truncated;
- raw canary exception messages, args, paths, bodies, IDs, endpoints, and
  subprocess output never appear in state, output, `str`, or `repr`;
- known `VerificationError` output remains unchanged;
- no `BaseException` control-flow conversion;
- source/call-site coverage for every required stage and no broad arbitrary
  exception output.

Preserve all 61 existing verifier tests and every fixture, catalog, provenance,
image, command, observer, accounting, and privacy negative. Before the one
diagnostic reproduction, complete:

- complete `tests/unit/test_codex_0149_assistant_output_history.py`;
- active OAP governance tests;
- Python compilation, Ruff check, and repository format check on both changed
  Python paths;
- exact diagnostic stage/category/progress/privacy tests;
- retained exact package preflight, manifest/integrity/path/size/digest/version
  tests and Local-005-q catalog source checks;
- `git diff --check`, exact allowed-path proof, and no report collision;
- push the final non-report implementation head to PR #298 and require all ten
  normal Gateway CI/CodeQL checks successful on that exact head.

Skipped, xfailed, missing, cancelled, pending, neutral, stale-head, or
environment-blocked required evidence is not a pass. In-scope diagnostic/test
failures may be repaired before the run. Once the real run begins, no verifier,
test, order, active-pointer, or product mutation is authorized.

## One fresh diagnostic reproduction

After all preflight and implementation-head checks pass, run exactly one fresh
zero-retry 161-f reproduction with the unchanged topology:

```text
exact task-local Codex 0.149.0 launcher/native provenance
  -> exact Local-005-q vision catalog
       -> unchanged Gateway production behavior
            -> signed fake Local
                 -> fake provider
```

This is not a rerun or amendment of 161-e. Acceptance paths are:

1. If the exact prior target is established—Gateway statuses `200,200,400`,
   first full-image wire class, resumed crop-image wire class, prior assistant
   `output_text` with exact fields `type,text` and bounded nonempty Unicode,
   exact rejection `responses_input_content_part_not_supported` at
   `input[5].content[0].type`, fake Local exactly two signed requests with one
   function and one message lifecycle, zero rejected-turn side effects, and
   complete cleanup—emit the unchanged fixed success line and report PASSED.
2. Otherwise emit one fixed FAILED result with the exact closed primary stage,
   exception category or existing `VerificationError` code, safe Gateway/Local
   progress, and cleanup booleans. A report may set diagnostic accepted YES
   only when every emitted field belongs to the reviewed closed vocabulary and
   no raw value survives.

Run no second reproduction. Do not steer prompts/catalog/commands, make a
correction after the result, access a protected service, or infer product
behavior from an unexpected failure.

## Security, privacy, accounting, and setup boundaries

Routine task-local npm/network installation and safe disposable PostgreSQL
setup are authorized exactly as in 161-e. Never run destructive setup against
`DATABASE_URL`; use only generated test state and verify cleanup. No apt-based
PostgreSQL install is requested.

No production/protected credential, Local PR mutation, Qwen/protected model,
real provider, hosted tool, connector, deployment, cutover, release, or
production system is authorized. Synthetic credentials remain ephemeral.
PostgreSQL remains accounting truth and the expected third request remains a
pre-admission rejection with no new reservation, ledger, or replay side effect.

No prompt, completion, assistant text, reasoning, media, body, stream, tool
argument/result, raw ID, secret, signature, endpoint, database URL, private
path, environment value, package-manager output, exception text, traceback, or
arbitrary type name may enter logs, reports, commits, or durable evidence.
Documentation is checked and no update is needed because this is verifier-only
diagnostic work with no compatibility claim.

## Publication and stop law

Preserve all prior orders/reports byte-for-byte. Commit and push the unchanged
161-f order and `oap/active` with diagnostic/test changes to the same PR branch.
Record the literal final non-report implementation head, including any repair
made before the run. Execute the one reproduction only from that exact clean
committed head after all ten checks pass. After the run begins, publish exactly
one immutable report with no other mutation:

`oap/reports/161-f-localize-unexpected-reproduction-failure.md`

The report must contain `RESULT=PASSED|FAILED`, literal implementation SHA,
`Report publication commit: SELF`, exact topology/diff, retained provenance
and preflight evidence, implementation-head checks, exactly-one-run evidence,
the exact closed stage/category/progress/cleanup result, every target predicate,
privacy/accounting/no-side-effect evidence, documentation impact, skips and
deviations, and:

```text
PREFX-DIAGNOSTIC-ACCEPTED = YES|NO
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
parent, and is the verified remote PR #298 head before response `OK`. Report-
head checks may be pending then; strategic verifies every final-head check.
Coding never merges or enables auto-merge. Return to the permanent control-wake
helper. Strategic alone decides the next continuation.
