# OAP Work Order — 155-aj

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Starting remote head: a9625753716325bc0ef6a75689bf42bddbfbd03d
Functional implementation head: 3cce1a7612fc9919adf26df9952baabaf703c348
Functional implementation tree: 8545cabd37cccf436da45fda7316d6654e53b4ad
Exact Local Coding authority: 4d3ab2fd97d249710f952dd3d2c28936138cc8fa

## Exact authority, objective, and non-goals

The human explicitly authorizes this final exact Objective-155 naming/scope
exception, `155-aj`, on existing PR #291 from immutable 155-ai FAILED report
head `a9625753716325bc0ef6a75689bf42bddbfbd03d`.

155-aj is the Objective-155 verifier/conformance cleanup and final hook-free
acceptance objective. It adds no compatibility feature. It does not authorize
`155-ak`, Local Coding or Qwen changes, replay-policy relaxation,
signed-identity redesign, production SSE-validator relaxation, new provider
behavior, broad refactoring, merge, auto-merge, cutover, or release.

Preserve unchanged from functional head
`3cce1a7612fc9919adf26df9952baabaf703c348`:

- Local-Coding signed-identity grammar representation/validation;
- Codex-0.149 visible reasoning;
- null-encrypted handling;
- ID-less function/custom tool-call handling;
- call-ID-HMAC replay semantics;
- route/tool/hosted-authority behavior;
- accounting/quota and production SSE state machine.

The only permitted `app/` change is deletion of the previously introduced
Objective-155 diagnostic-only qualification hook from
`app/slaif_gateway/services/responses_gateway.py`, including imports/constants/
helpers used solely by that hook. Preserve every prior activated order/report
byte-for-byte.

## Verified starting state

- PR #291 is OPEN, non-draft, MERGEABLE/CLEAN, unmerged, with no auto-merge.
- Remote PR head and clean task worktree are exactly
  `a9625753716325bc0ef6a75689bf42bddbfbd03d`.
- That report-only commit changes only
  `oap/reports/155-ai-signed-identity-grammar-interoperability-and-acceptance.md`;
  its first parent is functional implementation head
  `3cce1a7612fc9919adf26df9952baabaf703c348`; RESULT=FAILED.
- All ten checks pass on the immutable 155-ai report head. Remote `main`
  remains `7ffce834915b74809109e8b579d8541cdcfa9df7`.
- Local Coding is read-only and clean at exact PR #7 report head
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`.
- No 155-aj order/report existed before activation.
- The owner-only mode-0600 runtime reference has only the approved
  endpoint/credential-source keys; unchanged protected model discovery returned
  2xx. Never print or retain either value.
- The coding agent was blocked on the exact Gateway control FIFO.
- Governance currently permits through exact `155-ai`. Add only exact
  `155-aj`; keep `155-ak`, later multi-letter forms, and the next numeric
  objective rejected.

## Fixed interpretation of 155-ai

Treat the immutable 155-ai live evidence as a functional production-path proof:

- exact task-local Codex 0.149.0 ran and exited successfully;
- Gateway captured two requests and two 2xx SSE responses;
- Local received both requests and returned two 2xx SSE responses;
- both signed identities passed grammar, cardinality, service Bearer,
  exact-body, signature, route, method/path/query, version, timestamp, nonce,
  and internal-header predicates;
- Qwen received two inference requests and returned two successful 2xx SSE
  terminal completions;
- Local/Qwen completion predicates were valid;
- two reservations and two ledger rows finalized; zero remained pending;
- no Local/Qwen/provider error ownership exists for that run.

Do not make another production compatibility correction.

The sole 155-ai failure was verifier-owned:
`producer_boundaries_valid_verifier_expectation_wrong`. The verifier projected
34 and 24 already-reviewed reasoning-lifecycle events as `other`, set
`unknown_events=true`, and then rejected its own Gateway-facing structure.

## 1. Exact verifier reasoning-event vocabulary

Source-review the production
`ResponsesStreamEventValidator.validate()` implementation at functional head
`3cce1a7...`, specifically the exact active profile where
`codex_reasoning_events=true` and
`codex_0149_function_tool_events=true`.

The verifier-owned closed vocabulary must recognize the exact production-
reviewed events used by that branch:

    response.reasoning_part.added
    response.reasoning_text.delta
    response.reasoning_text.done
    response.reasoning_part.done

Add only names actually accepted by the active production branch. Do not
wildcard `response.reasoning_*`, copy the entire generic Codex set, or add
reasoning-summary/custom/hosted events not accepted by this exact state machine.

Mechanically source-check or AST-check the verifier set against the exact
production branch. Prove:

- one complete ordered reasoning lifecycle is recognized with exact counts;
- `unknown_events=false`;
- function-call and assistant-message lifecycles remain exact;
- an arbitrary syntactically similar unreviewed event maps to `other` and sets
  `unknown_events=true`;
- malformed/orphan/duplicate/reordered reasoning remains invalid despite known
  names;
- the vocabulary contains no prefix, regex, startswith, or wildcard growth.

The verifier stays independent. Do not modify
`app/slaif_gateway/providers/streaming.py` or weaken its validation.

## 2. Complete snapshot predicate matrix

Add explicit independent tests for every significant snapshot/diagnostic
predicate. The final report must contain an obligation table mapping each item
below to at least one concrete passing test name:

- non-list, missing, wrong, and excessive structure count;
- absent ordinal 0 and absent ordinal 1;
- `invalid=true`;
- missing and duplicate `response.created`;
- missing and duplicate `response.completed`;
- response-ID relationship false;
- wrong created status;
- wrong completed status;
- model mismatch;
- missing and invalid terminal output;
- missing and invalid completed usage;
- duplicates;
- genuinely unknown event;
- error event;
- trace overflow;
- abnormal/non-normal close;
- downstream early close;
- handler error;
- upstream truncation;
- function lifecycle mismatch;
- reasoning lifecycle mismatch;
- assistant-message lifecycle mismatch;
- snapshot schema/enum/cardinality/tamper/privacy-canary rejection;
- failure snapshot survival through cleanup and CLI emission.

Do not use one generic sanitizer test as a substitute. Each test must assert the
specific safe predicate/class it changes and show unrelated facts remain
bounded.

Exercise the full closed outcome classifier with independently constructed
supporting ordinal/count/status/terminal facts:

1. `local_turn2_rejected_before_qwen`;
2. `local_invoked_qwen_turn2_qwen_rejected_or_failed`;
3. `qwen_turn2_completed_local_stream_invalid`;
4. `local_qwen_turn2_completed_gateway_stream_invalid`;
5. `producer_boundaries_valid_verifier_expectation_wrong`;
6. `full_two_turn_path_succeeded`;
7. `other`.

No outcome may be selected from a status name alone when the required ordinal
and terminal evidence is absent.

## 3. Complete HMAC rotation tests; production replay frozen

Do not change production replay code. Add tests and list each exact test name in
the report proving:

- old v1 present-item reference verifies after v2 activation while v1 secret is
  configured;
- old v1 ID-less call-ID reference verifies under the same rotation;
- a new v2 function-call reference verifies by present item ID;
- that same new v2 function call verifies through ID-less call-ID lookup;
- equivalent present/ID-less v2 custom-tool-call verification, because custom
  replay is implemented;
- absent old v1 material rejects the old present-item lookup;
- absent old v1 material rejects the old ID-less call lookup;
- wrong present item ID plus correct call ID never downgrades;
- deterministic cross-version duplicate/ambiguous call matches reject;
- stored-row HMAC version mismatch rejects;
- active-version overflow/unavailable material rejects;
- raw item ID, call ID, HMAC digest, and privacy canary never enter
  exceptions, logs, CLI output, reports, or safe evidence.

Retain same-key/kind/tool/expiry/route/provider/model and PostgreSQL truth.
If a test exposes a production defect, do not fix it in 155-aj; publish FAILED
and stop before protected traffic.

## 4. Complete actual-Local matrix

Run a finite deterministic matrix with at least 16 synthetic combinations
spanning multiple owner UUIDs, Gateway-key UUIDs, canonical session UUIDs, and
repository scopes. It must include fixed UUID/domain/input cases whose legacy
pre-fix principal/session/repository encoding began with `-` and with `_`.

For every row use corrected Gateway derivation/signing and the actual unchanged
Local `verify_signed_identity()` at exact head
`4d3ab2fd97d249710f952dd3d2c28936138cc8fa`. Prove:

- all four Local grammar predicates;
- exact-body signing and Local acceptance;
- body tamper rejection with fresh replay state;
- signature tamper rejection;
- nonce replay rejection;
- raw owner/key/session/repository source inputs absent from derived identity,
  retained evidence, logs, and exceptions.

Before execution prove the Local commit and cleanliness. Set
`sys.dont_write_bytecode` or equivalent task isolation and restore it, leaving
no sibling bytecode. Retain only row count and booleans.

## 5. Execute unchanged pinned Codex-0.148 test

Install an exact disposable task-controlled `@openai/codex@0.148.0`. Do not
alter host `/usr/bin/codex`.

Run the unchanged
`tests/unit/test_qwen38_text_codex_candidate.py` inside a disposable isolated
mount namespace or container where only the isolated `/usr/bin/codex` path is
bound to a wrapper/executable for that exact install. Before the test prove:

- package name exactly `@openai/codex`;
- package metadata version exactly `0.148.0`;
- `--version` exactly `codex-cli 0.148.0`;
- isolated `/usr/bin/codex` invokes that exact verified task install;
- host `/usr/bin/codex` identity/version remains unchanged before/after.

Do not edit, exclude, skip, xfail, monkeypatch away, or weaken the test. If it
genuinely fails under exact 0.148.0, record only its fixed safe test/stage class,
publish RESULT=FAILED, and stop before protected traffic.

## 6. Remove all production SLAIF_155X qualification hook machinery

From
`app/slaif_gateway/services/responses_gateway.py` remove only:

- `_QUALIFICATION_HOOK_ENV`;
- `_QUALIFICATION_ARTIFACT_ENV`;
- `_QUALIFICATION_ROOT_ENV`;
- qualification-only event/field regexes, type sets, size/count constants;
- `_qualification_type_class`;
- `_qualification_name`;
- `_qualification_fields`;
- `_qualification_profile`;
- `_record_qualification_rejection`;
- its stream-rejection invocation;
- imports used solely by this machinery.

Do not change the surrounding invalid-stream decision, provider-failure
classification, error code, safe message, accounting/finalization, stream
state, or forwarding logic.

Replace verifier tests that called the production writer with verifier-owned
snapshot/fake evidence. The external verifier may retain task-local diagnostic
support outside `app/`, but fake validator-failure evidence must no longer
depend on setting a production hook.

Add AST/source and behavior gates proving:

- no `SLAIF_155X_` string anywhere below `app/`;
- no qualification artifact writer/path below `app/`;
- no file/network/raw-value sink was added;
- invalid provider event handling returns the same fixed error/accounting
  behavior as functional head `3cce1a7...`, except the diagnostic side effect
  is absent;
- hook environment variables cannot change production behavior.

## 7. Freeze every other production semantic

Before protected traffic, mechanically diff
`3cce1a7612fc9919adf26df9952baabaf703c348` to the candidate. Under `app/`,
the only allowed delta is deletion of the qualification hook machinery and
directly dependent imports/helpers in `responses_gateway.py`.

No modification is permitted to Codex normalization, reasoning/tool-call
validation, replay/HMAC code, signed identity, Local adapter/contract, route
semantics, production SSE validation, providers, quota, accounting, schema, or
dependencies. A non-deletion or unrelated app delta requires RESULT=FAILED and
stop.

## 8. Full pre-protected gate

Before protected traffic, all of these must pass:

- exact verifier reasoning vocabulary and wildcard/unknown negatives;
- complete per-predicate snapshot obligation matrix;
- all six post-forwarding outcomes plus `other`;
- complete item/call HMAC rotation/no-downgrade/ambiguity matrix;
- actual Local matrix with at least 16 rows and both legacy punctuation cases;
- unchanged pinned-0.148 test in its isolated exact executable environment;
- Codex-0.149 source and task-local provenance gates;
- visible-reasoning/null-encrypted/ID-less-tool-call regressions;
- hook-removal AST/source/behavior equivalence;
- fake prefixed-ID two-turn;
- fake non-prefixed/ID-less two-turn;
- fake provider failure;
- fake validator failure using verifier-owned evidence only;
- PostgreSQL replay tests executed without skip;
- PostgreSQL context/accounting tests executed without skip;
- privacy/source/scope/diff checks;
- Ruff/format/compile/documentation hygiene;
- full relevant unit/integration suites without unexplained exclusion;
- all ten PR checks green on the exact clean candidate head.

Use unique task-owned containers/databases/namespaces and remove them. Skipped,
xfailed, cancelled, pending, neutral, excluded, silently replaced, or
environment-failed required evidence is not a pass. If any gate fails, publish
RESULT=FAILED and do not send protected traffic.

## 9. Exactly one final hook-free protected qualification

Only after section 8 is fully green, execute exactly one zero-retry process:

task-local Codex 0.149.0 -> cleaned Gateway -> unchanged Local Coding at
`4d3ab2f...` -> unchanged protected Qwen.

Before execution prove `SLAIF_155X_` and production qualification-hook symbols
are absent from the exact candidate source. Require:

- exact Codex 0.149.0 package/catalog/executable provenance;
- two Gateway requests and two Gateway 2xx SSE responses;
- two Local requests and two Local 2xx SSE responses;
- both signed identities valid;
- two Qwen inference calls and successful terminal completions;
- turn-1 reasoning/function lifecycle valid;
- turn-2 reasoning/assistant-message lifecycle valid;
- the four reviewed reasoning names counted exactly, not `other`;
- `unknown_events=false` at Gateway-facing structures;
- no error event;
- normal closes and no early close/handler error/truncation;
- Codex exit success;
- exactly two finalized reservations and two finalized ledgers;
- zero pending;
- hosted-search/MCP/provider authority remains denied;
- replay, route, privacy, and accounting invariants green.

If the run fails, publish the complete safe snapshot and stop. Do not make
another correction or retry in 155-aj.

## Allowed paths

    app/slaif_gateway/services/responses_gateway.py
    scripts/verify_local_coding_full_stack.py
    tests/unit/test_local_coding_full_stack_verifier.py
    tests/unit/test_responses_codex_streaming_tools.py
    tests/unit/test_codex_replay_service.py
    tests/unit/test_local_coding_server_module.py
    tests/integration/test_codex_replay_references_postgres.py
    tests/integration/test_codex_context_accounting_postgres.py
    tests/unit/test_oap_governance.py
    oap/active
    oap/orders/155-aj-final-hook-free-objective-155-acceptance.md
    oap/reports/155-aj-final-hook-free-objective-155-acceptance.md

The unchanged pinned-0.148 test may be executed but not modified. No other
`app/` file, documentation, Local/Qwen/Codex source, migration/schema,
dependency, lockfile, registry/pair, prior order/report, AGENTS/OAP protocol,
release, or unrelated file change is authorized.

## Privacy, cleanup, report obligation table, and disposition

Retain no protected prompt/reasoning, raw request/response/SSE/header/body,
identity/session/item/call/owner/key/nonce/signature value, HMAC/body digest,
credential, endpoint, tool value/schema, arbitrary exception text, or temporary
path. Synthetic values remain test-only.

At closure remove the runtime reference and every exact 155-aj task root,
Codex install, mount/container/database/namespace, artifact, process, listener,
and bytecode tree. Preserve protected Qwen and unrelated state. Leave both
worktrees clean and restore host `/usr/bin/codex` unchanged.

Before creating the report, prove no `oap/reports/155-aj-*` exists. Publish
exactly one immutable report-only SELF commit whose first parent is the
terminal candidate implementation head and whose only changed path is:

    oap/reports/155-aj-final-hook-free-objective-155-acceptance.md

Never amend it. The report must contain an explicit table mapping every
section-2 predicate/outcome and every section-3 rotation requirement to its
concrete passing test name. It must record the actual-Local row count/cases,
isolated 0.148 provenance/result, exact hook-removal app diff, fake/PostgreSQL/
CI results, one protected snapshot/result, cleanup, topology, and limitations.

RESULT=PASSED requires every test/conformance debt plus the single hook-free
protected qualification. If passed, state only:

> Objective 155 technical acceptance established; exact Gateway and Local
> heads ready for post-acceptance integration review.

That is not merge, release, or cutover approval. PR #291 remains unmerged and
returns to strategic review for the planned cleanup/splitting review and Local
Coding OAP-005 resumption.

Do not merge, auto-merge, activate `155-ak`, or infer later work. Require all
ten checks green on the immutable report head, send exactly two response FIFO
bytes `OK` once, return to one blocking control-FIFO read, and stop.
