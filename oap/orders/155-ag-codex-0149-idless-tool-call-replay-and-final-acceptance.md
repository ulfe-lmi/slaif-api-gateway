# OAP Work Order — 155-ag

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Starting remote head: 37e923304cf4b1cdb4fb9f8faefe4a7b2fb6db6e

## Exact authority, objective, and non-goals

The human explicitly authorizes this one exact naming/scope exception, `155-ag`,
on existing PR #291 from immutable 155-af FAILED report head
`37e923304cf4b1cdb4fb9f8faefe4a7b2fb6db6e`.

This is a narrow Codex-0.149 tool-call replay-identity compatibility correction
and final acceptance attempt. It does not authorize `155-ah`, a general
multi-letter scheme, broad Objective-155 refactoring, Local Coding or Qwen
changes, arbitrary replay weakening, fabricated IDs, merge, auto-merge, cutover,
release, or unrelated cleanup.

Preserve unchanged:

- the permanent 155-ae visible-reasoning implementation;
- the 155-af `encrypted_content:null` detector correction;
- all previous activated orders and reports, especially the immutable 155-af
  report exactly as published.

Prospectively repair the three safe-class mappings omitted by 155-af. Never
amend or reinterpret that prior report.

## Verified starting state

- PR #291 is OPEN, non-draft, MERGEABLE/CLEAN, unmerged, with no auto-merge.
- Remote PR head and the clean task worktree are exactly
  `37e923304cf4b1cdb4fb9f8faefe4a7b2fb6db6e`.
- That report-only commit changes only
  `oap/reports/155-af-null-encrypted-replay-detector-and-final-acceptance.md`;
  its first parent is implementation head
  `34ab5afd09af026286779838db21cddad1717877`; its result is FAILED.
- All ten checks pass on the immutable 155-af report head.
- Remote `main` remains `7ffce834915b74809109e8b579d8541cdcfa9df7`.
- Local Coding remains read-only and Git-clean at PR #7 report head
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`, implementation parent
  `258ae2ebad39651076937b9f027e60831b8d2786`.
- No 155-ag order/report existed before activation.
- The exact owner-only mode-0600 runtime reference has only the two approved
  endpoint/credential-source keys; its credential source is owner-only. The
  unchanged protected model discovery preflight returned 2xx. Do not print or
  retain either value.
- The repository active-selector governance currently permits through exact
  `155-af`. Add only exact `155-ag`; keep `155-ah` and generalized forms
  rejected.

## Pinned source authority to prove before product modification

Use the official OpenAI Codex annotated tag `rust-v0.149.0` (tag object
`a4e15bf371341b067c8278d3b70b1a8c7b3d793e`), which dereferences to exact
commit `758ef40f50c1a458425c7cfbf1eb12cbc07af0b0`. Do not use current-main
assumptions.

Before changing Gateway product behavior, prove from that exact source:

1. In `codex-rs/protocol/src/models.rs`,
   `ResponseItem::FunctionCall.id` and
   `ResponseItem::CustomToolCall.id` are optional while their `call_id`
   fields are mandatory strings.
2. Their matching function/custom output item IDs are optional while output
   `call_id` remains mandatory.
3. In `codex-rs/protocol/src/response_item_id.rs`,
   `ResponseItemId::is_prefixed()` requires a nonempty prefix and suffix
   separated by an underscore.
4. In `codex-rs/core/src/client.rs`,
   `ModelClient::prepare_response_items_for_request()` clears an existing ID
   when `is_prefixed()` is false and does not generate any replacement.
5. That preparation is applied to the formatted input immediately before the
   HTTP Responses `stream_request` and the corresponding WebSocket request
   construction.

Record only source paths, tag/commit identities, structural facts, and
content-free test classes.

## Mandatory pre-fix actual-Codex reproduction

Do not change product behavior until this reproduction succeeds.

Extend only the disposable verifier/fake-provider harness to run the actual
task-local `@openai/codex@0.149.0` executable against the current Gateway
behavior. The fake turn-1 provider stream must return an otherwise valid,
approved local function call with:

- a bounded syntactically valid but deliberately non-prefixed item ID for which
  exact Codex 0.149 `ResponseItemId::is_prefixed()` is false;
- a valid bounded `call_id`;
- an approved local function declaration;
- no hosted-tool authority.

Let that exact Codex process naturally execute the local tool and issue its
second request. Prove with bounded evidence that it:

- omits the non-prefixed function-call item ID;
- preserves a valid `call_id`;
- emits the adjacent matching function-call output bound by that `call_id`;
- receives the current Gateway rejection safe family
  `codex_tool_roundtrip_invalid` at item field `id`;
- never reaches the fake Local/Qwen provider for turn 2;
- creates accounting only for the actually admitted turn and leaves zero
  pending state.

Do not replace the pinned executable with a handcrafted envelope. The harness
may inspect transient values only to compute the closed facts below and must
discard them immediately. Persist/output only:

- selected tool-call type: `function` / `custom` / `other`;
- item-ID state: `absent` / `null` / `present`;
- when present, prefix predicate:
  `codex_prefixed` / `other`, where `codex_prefixed` means the exact
  source `is_prefixed()` predicate; never retain the prefix or ID;
- call-ID state: `present_valid` / `absent_or_invalid`;
- adjacent matching output: boolean;
- fixed Gateway code/parameter classes and bounded hop/accounting counts.

If this exact actual-Codex pre-fix reproduction does not match the 155-af
mechanism, publish RESULT=FAILED and stop. Do not implement the correction.

## Architectural rule and declarative client policy

Only after the mandatory reproduction succeeds, implement this rule:

> For the exact Codex-0.149 client dialect, an absent/null function/custom
> tool-call item ID is valid only when the call remains authenticated as prior
> provider output through its existing `call_id`. Never invent an item ID and
> never bypass replay ownership.

Express the dialect in `ResponsesClientPolicySpec`, with strict default-false
facts equivalent to:

- function-call item ID may be absent/null;
- custom-tool-call item ID may be absent/null;
- an ID-less tool-call replay candidate may use an authenticated call-ID
  anchor.

Enable all three only for exact `codex-0.149-responses-v1`. The static
registry must continue to give that client exactly one reviewed pairing:
`local-coding-v1`. Default/OpenAI, Codex 0.147, arbitrary client modules,
hosted-tool routes, and any unreviewed server pairing remain strict. Do not put
database, routing, provider, quota, or other Gateway authority in the client
module. Do not scatter concrete `if codex_0149` branches through core.

## Exact request/tool validation behavior

For the selected authorized spec only:

- accept a function/custom call whose item `id` is absent or null;
- preserve absence versus explicit null semantically and never synthesize,
  hash-generate, UUID-generate, position-generate, infer, or reconstruct an ID;
- validate any present ID exactly as today, including bounds and uniqueness;
- keep `call_id` mandatory, bounded, and unique;
- keep exact approved tool taxonomy, name/namespace/status, arguments/input,
  item/cardinality/aggregate bounds, and immediate matching output order;
- preserve current permission for a matching function/custom output to omit its
  own item ID; do not broaden null/malformed output IDs without direct evidence;
- continue binding call and output by exact `call_id`;
- reject present malformed/empty IDs rather than downgrading to ID-less mode.

Ordinary/default function/custom call validation remains unchanged. Reasoning
and compaction replay gain no call-ID fallback. The separate 155-ae ID-less
visible-reasoning path creates no replay candidate.

## Replay ownership using the existing call-ID HMAC

The existing PostgreSQL design is authoritative and must remain HMAC-only:

- `item_id_hmac` remains non-null and uniquely constrained by
  gateway-key/item-kind;
- function/custom rows already persist `call_id_hmac`, tool namespace/name,
  HMAC key version, provider, route, upstream model, source ledger/request, and
  expiry;
- `uq_codex_replay_references_key_kind_call` and
  `ix_codex_replay_references_key_kind_call_expiry` already exist.

No migration or model/schema change is authorized unless direct source
inspection disproves those facts; if disproved, stop instead of adding schema
work.

Add a bounded repository lookup by same-key active
`(item_kind, call_id_hmac)` digest tuples. Extend the transient request replay
candidate so a function/custom call keeps mandatory `call_id` while `item_id`
may be absent only when the selected client spec authorizes fallback.

Ownership verification must be exactly:

### Present item ID

- retain the current item-ID HMAC lookup;
- require the persisted call-ID HMAC and tool facts to match too;
- never retry or downgrade to call-ID-only lookup when the supplied item ID is
  wrong, unknown, expired, or mismatched.

### Absent/null item ID

- permit only an authorized function/custom candidate;
- compute call-ID HMAC candidates under the bounded active HMAC versions;
- query only the same Gateway key, same item kind, unexpired rows, by call-ID
  digest;
- require exactly one row across all active versions;
- require its HMAC key version to match the digest secret used;
- constant-time verify the call-ID digest and verify item kind, tool namespace
  and name, plus every existing content-free stored binding;
- after route resolution, require the same provider, route, and upstream-model
  compatibility as present-ID replay.

Unknown, zero-match, ambiguous, duplicate, expired, cross-key, wrong kind/tool,
wrong route/provider/model, malformed/oversized call ID, and unavailable HMAC
material fail closed before quota reservation or provider side effects.
Repository errors fail closed. Do not persist raw IDs, call IDs, or new weaker
identifiers.

## Required policy/replay/security tests

Before protected traffic, prove at minimum:

- exact 0.149 ID-less function call plus known matching call-ID HMAC succeeds;
- exact 0.149 ID-less custom call plus known matching call-ID HMAC succeeds for
  the already-supported custom shape;
- present prefixed item-ID behavior is unchanged;
- present correct item ID plus correct call ID succeeds;
- present wrong item ID plus correct call ID fails without fallback;
- absent item ID plus unknown/expired call ID fails;
- cross-key call ID fails;
- cross-route/provider/upstream-model call ID fails;
- wrong item kind, tool name, or namespace fails;
- duplicate call ID, call/output mismatch, output without approved call, and
  malformed/oversized call ID fail;
- default/OpenAI and Codex 0.147 missing tool-call IDs remain strict;
- reasoning/compaction cannot use call-ID fallback;
- active/retiring HMAC versions work for both item- and call-ID lookup;
- active-version overflow/unavailable keys, repository failure, zero and
  ambiguous matches fail closed;
- PostgreSQL proves the existing call-HMAC uniqueness/index contract and
  same-key/expiry behavior; item-ID uniqueness remains unchanged;
- ownership and route checks occur before quota/provider side effects;
- no raw item/call IDs or digest values enter logs, metrics, audit, errors,
  reports, or fixtures.

## Prospective 155-af verifier conformance repair

Without amending 155-af, add the three previously omitted closed Gateway
mappings:

- `responses_codex_encrypted_reasoning_replay_not_allowed`;
- `responses_codex_reasoning_visible_invalid`;
- `responses_codex_reasoning_visible_too_large`.

Retain exact `responses_codex_tool_roundtrip_invalid`, replay, route, and
request-policy mappings. Add pure tests for every mapping, ordinal alignment,
unknown/cross-boundary fallback to `other`, malformed/tampered evidence, and
privacy canaries.

Add the bounded selected-tool-call projection from the mandatory reproduction:
tool type, item-ID state, exact prefix-predicate class, call-ID validity class,
and adjacent matching-output boolean. Never retain identifiers, prefixes,
namespaces/names, arguments/results, schemas, or bodies.

## Fake and pre-protected acceptance

After the source proof and product implementation, but before protected
traffic, pass:

1. the mandatory non-prefixed-ID actual pinned-Codex reproduction against
   pre-fix behavior, retained only as bounded proof;
2. a recognized/preserved item-ID actual-Codex path;
3. ID-less call-ID ownership success;
4. forged/expired/cross-key/cross-route/provider/model/tool/HMAC negatives;
5. ordinary two-turn actual Codex qualification through Gateway to fake
   Local/Qwen;
6. provider-failure and validator-failure accounting matrices;
7. two admitted success turns producing exactly two coherent finalized
   reservation/ledger outcomes and zero pending;
8. focused client-policy, request-policy, replay-service, Gateway-pipeline,
   streaming/replay, privacy, source, schema/index, PostgreSQL, accounting, and
   official-client E2E tests;
9. full Ruff/format/compile/diff/scope checks and all ten PR checks on the exact
   clean implementation head.

No protected request occurs before the exact implementation head is pushed,
remote-matched, clean, and all ten checks are successful. Skipped, missing,
pending, cancelled, or neutral checks are not passes.

## Exactly one protected diagnostic

Run exactly one zero-retry process:

real task-local Codex 0.149.0 -> Gateway -> unchanged Local Coding at
`4d3ab2f...` -> unchanged protected Qwen.

Do not steer prompt, tools, route, model, or configuration around the observed
path. Acceptance requires:

- turn 1 reaches Local and Qwen exactly once, returns valid 2xx SSE, and closes
  normally;
- Codex naturally issues its function-result continuation;
- 155-ae visible ID-less reasoning remains accepted and unchanged;
- 155-af null encrypted content remains on the visible path;
- if Codex strips the provider tool-call item ID, Gateway authenticates the
  continuation through the persisted same-key call-ID HMAC;
- no item ID is manufactured;
- function call/output remain one exact adjacent call-ID-matched pair;
- turn 2 passes Gateway and reaches Local/Qwen once;
- the final assistant/message lifecycle completes normally;
- no Gateway 4xx, stream-validation failure, or Gateway-induced Local
  disconnect occurs;
- every admitted request has coherent terminal accounting and zero pending;
- signed identity, HMAC replay, route containment, hosted-search denial, and
  privacy checks remain green.

If Gateway rejects for a different reason, publish its exact improved closed
classification and stop. If turn 2 reaches Local but Local/Qwen rejects the
preserved ID-less tool-call state, publish that bounded boundary evidence and
stop. Do not retry or make a second product correction in 155-ag.

## Hook-free final

Only if the protected diagnostic succeeds completely:

1. remove every temporary `SLAIF_155X_*` qualification hook/writer and other
   diagnostic-only production machinery already required for removal;
2. retain permanent declarative client-policy, HMAC replay, security, schema,
   and ordinary hook-free verifier tests/capability;
3. prove diagnostic/raw-value sink and private artifact absence outside
   immutable OAP history;
4. run the full affected suite, PostgreSQL tests, privacy/source/scope checks,
   and all ten PR checks on the exact clean hook-free implementation head;
5. run exactly one fresh zero-retry hook-free protected two-turn qualification
   with all diagnostic acceptance criteria.

Only that fresh hook-free run may establish Gateway acceptance. If it fails,
publish the narrowest bounded failure and stop; do not retry.

## Documentation, privacy, and accounting

Update only affected wording in `docs/responses-compatibility.md`,
`docs/accounting.md`, and `docs/compatibility-matrix.md`:

- call-ID fallback is an exact Codex-0.149/client-pair dialect rule;
- raw item/call IDs and HMAC digests never persist or appear in evidence;
- PostgreSQL replay references remain content-free control metadata, not
  accounting truth;
- every admitted request still reserves/finalizes normally;
- a pre-admission replay rejection creates no dummy ledger row;
- compatibility remains unaccepted until the hook-free protected final passes.

Retain no real prompt/reasoning, body, raw SSE/header, item/call/session ID,
prefix/name, tool argument/result/schema, credential, endpoint, signature,
digest, canonical bytes, nonce/timestamp, arbitrary exception text, or
temporary path. Synthetic fake values are allowed only in tests and may not
resemble captured protected content.

At closure remove the private runtime reference and every exact 155-ag task
root, installed Codex, summary, process, listener, container, database,
bytecode, diagnostic artifact, and temporary file. Preserve unrelated state
and both worktrees. Do not stop or reconfigure protected Qwen.

## Allowed paths

    app/slaif_gateway/modules/contracts.py
    app/slaif_gateway/modules/clients/codex_0149.py
    app/slaif_gateway/services/responses_request_policy.py
    app/slaif_gateway/services/codex_replay_service.py
    app/slaif_gateway/db/repositories/codex_replay.py
    app/slaif_gateway/services/responses_gateway.py
    scripts/verify_local_coding_full_stack.py
    tests/unit/test_codex_client_modules.py
    tests/unit/test_responses_request_policy.py
    tests/unit/test_responses_codex_multiturn_replay.py
    tests/unit/test_codex_replay_service.py
    tests/unit/test_responses_codex_streaming_tools.py
    tests/unit/test_local_coding_full_stack_verifier.py
    tests/unit/test_alembic_codex_replay_references.py
    tests/integration/test_codex_replay_references_postgres.py
    tests/integration/test_codex_context_accounting_postgres.py
    tests/e2e/test_openai_python_client_responses.py
    docs/responses-compatibility.md
    docs/accounting.md
    docs/compatibility-matrix.md
    oap/active
    oap/orders/155-ag-codex-0149-idless-tool-call-replay-and-final-acceptance.md
    oap/reports/155-ag-codex-0149-idless-tool-call-replay-and-final-acceptance.md

No migration, database model, dependency, lockfile, server registry/pair,
Local/Qwen/Codex, prior order/report, AGENTS/OAP protocol, release, or unrelated
file change is authorized. `responses_gateway.py` may change only for the
minimum client-spec propagation, replay verification integration, and
post-success hook removal described above.

## Publication, immutable report, and response

Before creating the report, prove no `oap/reports/155-ag-*` exists. Publish
exactly one immutable report-only SELF commit whose first parent is the
terminal implementation head and whose only changed path is:

    oap/reports/155-ag-codex-0149-idless-tool-call-replay-and-final-acceptance.md

Never amend or replace it after publication. RESULT=PASSED requires both the
diagnostic and fresh hook-free protected final to satisfy every acceptance
criterion. Otherwise publish RESULT=FAILED with the narrowest privacy-safe
boundary evidence and stop.

The report must record source provenance, pre-fix actual-Codex proof, exact
declarative policy containment, HMAC lookup/no-downgrade behavior, schema
continuity, tests/checks, live hop/accounting counts, privacy/cleanup, exact
implementation/report topology, and any safe failure class. On pass only, post
the exact hook-free implementation and report heads to Local Coding PR #7.

Do not merge, auto-merge, activate 155-ah, or infer any later work. Require all
ten checks green on the immutable report head, send exactly two bytes `OK`
once to the response FIFO, return to one blocking control-FIFO read, and stop.

