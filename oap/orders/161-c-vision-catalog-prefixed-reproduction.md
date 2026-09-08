# OAP Work Order — 161-c

PR mode: `AMEND_EXISTING_PR`

## Objective

Amend Gateway Objective-161 PR #298 to correct the exact verifier-owned vision
catalog omission proven by immutable 161-b. Configure and validate the
task-local Codex 0.149 synthetic model with the complete Local-005-q-proven
vision capability facts, then run exactly one zero-retry pre-fix reproduction.

This remains a prove-before-fix verifier round. Do not modify production code
or documentation and do not implement assistant-history acceptance. If the
actual first full image and resumed crop reach Gateway and the exact assistant
`output_text` rejection is reproduced before Local, publish PASSED and stop for
strategic review. Any other result is FAILED and stops this round.

## Exact current state and reason

- Repository: `ulfe-lmi/slaif-api-gateway`.
- Round: `161-c`; amend existing PR #298. Do not create a new PR.
- PR/branch: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/298`,
  `oap/161-codex-assistant-output-history`.
- Base: exact `main` commit
  `910ddaa23763883c07f5d2065662eb1157deb9f1`.
- 161-b activation head: `f28f05c5998103530c010ff98a3ece55ecec44d6`.
- 161-b verifier implementation head:
  `be4e94c57fb7743fb944c9cf8b3a6fc5f48cd14d`.
- Immutable 161-b FAILED report head/current PR head:
  `c3201697068780af1c56b63766347cfbe639f6c1`.
- Report path:
  `oap/reports/161-b-exact-image-history-prefixed-reproduction.md`.
- The report commit changes only that report, its first parent is the literal
  implementation head, and all ten final-head checks are successful.
- PR #298 is open, non-draft, mergeable/CLEAN, and remains the only
  Objective-161 PR.
- No production or documentation path has changed in Objective 161.
- Historical PR #291 remains untouched and out of scope.
- Local PR #7 remains frozen at report head
  `5aec2beccc07432d45e936b82952abf52dfb10d8`, implementation parent
  `64e50172ee02563e2b021554f6b0d345cc7dfdec`.

161-b correctly implemented and unit-tested valid distinct RGB full/crop PNGs,
exact private-home `exec` / `exec resume --last` command binding, bounded image
wire classification, zero retry, privacy, and cleanup. Its one run stopped
before the first Gateway request with fixed class
`codex_first_turn_turn_failed_gateway_zero_status_none_error_other_param_other_local_zero`.

Source correlation proves a verifier-owned catalog mismatch:

- the Gateway verifier derives a generic synthetic capture model catalog and
  changes only `supports_image_detail_original` to `true`;
- it never declares `input_modalities=["text","image"]`;
- exact Local 005-q code at `64e50172...` makes vision explicit with
  `input_modalities=["text","image"]`,
  `supports_image_detail_original=false`, `context_window=100000`,
  `max_context_window=100000`, and
  `supports_parallel_tool_calls=false`;
- exact Codex 0.149 source consumes model image capability before request
  preparation, so the incomplete/text-oriented catalog can fail before HTTP.

Abort and report any discrepancy in PR/base/head/report topology or frozen
Local authority. Never create a replacement PR.

## Exact allowed paths

Only these paths may change:

- `scripts/verify_codex_0149_assistant_output_history.py`
- `tests/unit/test_codex_0149_assistant_output_history.py`
- `oap/active`
- `oap/orders/161-c-vision-catalog-prefixed-reproduction.md`
- `oap/reports/161-c-vision-catalog-prefixed-reproduction.md`

Do not change any app, accepted fixture, Objective-160 verifier/test, Local
module, replay/HMAC, database/schema/migration, dependency/lockfile, CI,
doctrine, or documentation path.

## Required correction

Preserve all 161-b fixture, argv, observer, fake-Local signing/lifecycle,
zero-retry, no-side-effect, privacy, and cleanup behavior. Correct only the
selected synthetic model catalog:

1. After deriving the installed 0.149 catalog schema, select exactly the one
   configured synthetic model by exact slug. Do not assume list position.
2. Set exactly these Local-proven vision facts on that selected model:

   ```text
   input_modalities = ["text", "image"]
   supports_image_detail_original = false
   context_window = 100000
   max_context_window = 100000
   supports_parallel_tool_calls = false
   ```

3. Preserve every unrelated generated catalog field and model identity. Do not
   add a newer-Codex field, provider capability, route authority, hosted-tool
   capability, or production model claim.
4. Write canonical bounded JSON mode 0600 under the task root. Re-read and
   validate the exact selected-model facts before launching Codex.
5. Add pure tests for exact positive facts and fail-closed missing model,
   duplicate model, malformed modalities, reversed/extra modalities, detail
   true/missing, invalid context values, parallel tools true/missing, unknown
   mutation, noncanonical/oversized catalog, and raw-value exclusion.
6. Add a source assertion tying these values to the immutable Local 005-q
   helper path and commit, without importing or modifying Local at runtime.
7. Verify task-local `@openai/codex@0.149.0` and the previously accepted binary
   SHA-256
   `bbc3341e44c9ead340ed9570c17be936e37870f570751a941699ffd04d672827`
   before the real run. Report only equality, never installation paths.

Do not alter the fake stream, prompts, tool lifecycle, image bytes, command
topology, request profile, Gateway app, or expected rejection to steer the
run. If the catalog does not explain the pre-network failure, retain one fixed
safe class and stop.

## One exact reproduction

After complete unit, catalog, governance, Ruff, format, compile, diff, privacy,
and cleanup preflight passes, run exactly one zero-retry reproduction:

```text
real task-local Codex 0.149.0 with exact vision catalog
  -> unchanged Gateway base behavior
       -> signed fake Local
            -> fake provider
```

Acceptance requires all of:

- exact package/version/binary provenance;
- validated exact vision catalog facts above;
- one private session, initial valid full-image command, natural function/
  result and assistant-message lifecycle, then natural `resume --last` with
  the distinct crop;
- actual Gateway progression `200,200,400`, request/stream retry count zero;
- actual first request full-image wire class and actual rejected resumed
  request crop-image wire class;
- resumed request prior role `assistant`, exact content part `output_text`,
  exact fields `type,text`, bounded nonempty valid-Unicode text classification,
  and exactly one expected crop image;
- exact safe rejection code
  `responses_input_content_part_not_supported` and parameter
  `input[5].content[0].type`;
- fake Local remains exactly two signed requests and does not advance on the
  rejected turn;
- rejected pre-admission request creates no reservation, ledger, replay, or
  other side effect;
- exact fixed success line and complete task-owned cleanup.

Retain only fixed versions/digests, booleans, ordinals, count/size/hash-equality
classes, field/type/role enums, status/code/parameter classes, Local delta,
retry count, and cleanup facts. Never retain or print prompts, assistant text,
images/data URLs, bodies/SSE, IDs/call IDs, headers, credentials/signatures,
endpoints, DB URLs, paths, or arbitrary errors.

If any required predicate fails, publish FAILED and stop. Do not run a second
real reproduction and do not make another correction in 161-c.

## Verification

Run complete:

- `tests/unit/test_codex_0149_assistant_output_history.py`;
- active OAP governance tests;
- Ruff check and repository format check on both changed Python paths;
- Python compilation on both changed Python paths;
- catalog canonicalization/source/privacy tests;
- `git diff --check` and exact allowed-path proof;
- the one exact reproduction only after every preflight passes;
- all ten normal Gateway CI/CodeQL checks on the exact final report head.

Skipped, xfailed, missing, cancelled, pending, neutral, stale-head, or
environment-blocked required evidence is not a pass.

## Boundaries and publication

No production behavior, documentation, Local code, protected service/traffic,
provider inference, PR #291, deployment, cutover, release, newer Codex,
OpenCode, Antigravity, or future Gateway objective is authorized. Coding never
merges or enables auto-merge.

Preserve the already-published strategic activation commit byte-for-byte.
Push verifier/test work to the same PR branch, record the literal final
non-report implementation head, and publish exactly one immutable report:

`oap/reports/161-c-vision-catalog-prefixed-reproduction.md`

The report must contain `RESULT=PASSED|FAILED`, literal implementation SHA,
`Report publication commit: SELF`, exact topology/diff, catalog source and
facts, preflight, one-run result, full/crop/history/error/Local/no-side-effect/
privacy/cleanup evidence, all ten final-head checks, and these labels:

```text
PREFX-REPRODUCTION-ACCEPTED = YES|NO
IMPLEMENTED = NO
TESTED = NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = NO
LOCAL-CROSS-CONTRACT-ACCEPTED = NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO
```

The final commit changes only the report, has the implementation head as first
parent, and is the verified remote PR #298 head before exact response `OK`.
Return to the control FIFO. Strategic alone decides the next continuation.
