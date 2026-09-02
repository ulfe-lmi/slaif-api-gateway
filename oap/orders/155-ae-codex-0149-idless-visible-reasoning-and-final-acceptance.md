# OAP Work Order — 155-ae

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: 22a15fd65c24f655448d1547bdb275634483c8e9

## Human-authorized exact exception and fixed architectural decision

The human explicitly authorized `155-ae` on existing PR #291 after immutable
155-ad FAILED report head `22a15fd65c24f655448d1547bdb275634483c8e9`.
This is one exact naming/scope exception. It does not authorize `155-af`, a general
multi-letter scheme, broad Objective-155 refactoring, Local Coding or Qwen changes,
fabricated reasoning identity, global OpenAI Responses relaxation, merge, auto-merge,
cutover, or release.

The architectural decision is fixed:

> Codex 0.149 state-bearing reasoning items may omit or null their reasoning ID.
> Validate and preserve that legitimate version-owned state under strict bounds. Do
> not strip it, fabricate an ID, or generalize the rule to ordinary OpenAI Responses.

The 155-ad observed item had nonempty visible content, empty summary, null encrypted
content, absent ID, the exact allowed key set, and no unexpected semantic fields. It
is state-bearing and is not an empty compatibility placeholder. Do not resurrect the
rejected empty-placeholder canonicalization.

## Objective

Express the exact Codex 0.149 reasoning-input dialect delta through the existing
`ResponsesClientPolicySpec` / static client-module architecture; preserve all generic
and default strictness; correct only the qualification accounting expectation for
pre-admission rejection; prove the real two-turn path once with bounded diagnostics;
then remove temporary qualification hooks and prove one fresh hook-free protected
two-turn acceptance on the final implementation head.

## Verified starting state

- PR #291 is OPEN, non-draft, MERGEABLE/CLEAN, unmerged, without auto-merge, at
  immutable report head `22a15fd65c24f655448d1547bdb275634483c8e9`.
- That report commit was created once, changes only
  `oap/reports/155-ad-local-error-stage-and-tool-choice-diagnostic.md`, and has first
  parent `407f75fe38643c0cfe8cf30a615449b91cf614ec`.
- All ten report-head checks pass. Remote `main` remains
  `7ffce834915b74809109e8b579d8541cdcfa9df7`; Gateway and Local worktrees are clean.
- Local Coding PR #7 remains read-only at report head
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`, implementation parent
  `258ae2ebad39651076937b9f027e60831b8d2786`, checkout
  `/home/ubuntu/codex-work/slaif-local-coding-005m`.
- 155-ad's single protected process used exact task-local Codex 0.149.0. Turn 1
  reached Local/Qwen and closed normally. Turn 2 reached Gateway with the adjacent
  function-call/output continuation and the state-bearing ID-less reasoning item,
  then received a Gateway 4xx before a second Local request.
- Turn-1 service Bearer, signed-header cardinality, exact-body HMAC, route,
  timestamp/nonce, internal-header, tool-policy transformation, and hosted-search
  containment checks passed.
- One reservation/ledger row finalized and zero remained pending. The existing
  qualification helper incorrectly expected a row for the second request even though
  it was rejected before admission/reservation.
- Current Codex 0.149 module version is `3`; current policy requires a reasoning ID
  and permits only null visible content in its encrypted-replay validator.
- The repository selector test permits ordinary one-letter IDs plus exact `155-aa`
  through `155-ad`; add only exact `155-ae` and keep `155-af` and every generalized or
  malformed multi-letter form rejected.
- Every earlier activated order and report is immutable. The private runtime
  reference will be supplied as an owner-only mode-0600 two-key file; never render or
  retain its values.

## 1. Pinned source authority and source-derived fixture

Use only the exact upstream OpenAI Codex release and commit below as the client
dialect authority, not current main, a mutable example, or public OpenAI API inference:

- repository: `openai/codex`;
- annotated tag: `rust-v0.149.0`;
- dereferenced commit: `758ef40f50c1a458425c7cfbf1eb12cbc07af0b0`.

Before product edits, independently verify and record these bounded source facts:

- `codex-rs/protocol/src/models.rs`: `ResponseItem::Reasoning` models
  `id: Option<ResponseItemId>`, `summary: Vec<ReasoningItemReasoningSummary>`,
  `content: Option<Vec<ReasoningItemContent>>`, and
  `encrypted_content: Option<String>`;
- the exact summary variant serializes as `{type: "summary_text", text: string}`;
- the exact visible content variants serialize as
  `{type: "reasoning_text", text: string}` and `{type: "text", text: string}`;
- `codex-rs/codex-api/src/common.rs`: `ResponsesApiRequest.input` is
  `Vec<ResponseItem>`;
- `codex-rs/core/src/client.rs`: normal request construction uses the formatted input
  directly, and `prepare_response_items_for_request` only clears an existing
  non-prefixed ID; it never generates an ID for an ID-less item.

Add one canonical, synthetic, content-safe source-contract fixture under
`tests/fixtures/codex/0.149.0/` containing the tag, commit, exact source paths, closed
field/type facts, and synthetic structural vectors. Do not copy real reasoning text,
prompts, IDs, tool content, or arbitrary source excerpts. Validate its canonical
bytes/schema and pin its digest in tests or the Codex module as appropriate.

As contrast, retain the pinned public OpenAI Responses contract used by this
repository: ordinary `ResponseReasoningItem` requires `id`, `summary`, and `type`.
Tests must prove the default/OpenAI behavior remains strict.

## 2. Represent the dialect delta in `ResponsesClientPolicySpec`

Extend the immutable client-policy spec with explicit, generic facts equivalent to:

- whether visible reasoning IDs may be absent/null;
- exact visible-reasoning content field set and allowed part types;
- maximum visible-reasoning parts;
- maximum bytes per visible-reasoning part;
- maximum aggregate visible-reasoning bytes per item/request as needed;
- whether ID-less encrypted reasoning is allowed (false for this objective).

Names may follow repository conventions, but the policy must be declarative and
inspectable. Defaults and every non-0.149 spec remain strict: reasoning ID required,
no new visible part vocabulary, and no ID-less encrypted state. Set the delta only in
`codex-0.149-responses-v1`, advance that module's reviewed version, and expose the
pinned source-contract provenance without changing its module ID.

Do not scatter `if codex_0149` branches through Gateway core. The generic validator
may consume the selected spec; it must not know a concrete module ID. The existing
static registry remains the pairing authority, and only the reviewed
`codex-0.149-responses-v1 -> local-coding-v1` selection can reach this behavior in the
application path.

## 3. Strict visible and encrypted reasoning validation

Refactor only the existing reasoning-item validator enough to support two explicit
modes selected from the client spec.

### Visible-state mode

For the exact 0.149 spec:

- require `type == "reasoning"`;
- permit `id` absent, explicitly null, or one existing valid bounded ID;
- never synthesize, hash, UUID-generate, position-generate, infer, or replace an ID;
- require `summary` to be a bounded array of exact `{type: "summary_text", text}`
  objects; preserve order and text exactly;
- when `content` is present, require a bounded array containing only exact
  `{type: "reasoning_text", text}` or `{type: "text", text}` objects;
- reject extra part fields, unknown part types, non-string text, malformed arrays,
  excessive part counts, excessive per-part bytes, excessive aggregate visible
  bytes, invalid Unicode, and request-level overflow;
- permit `encrypted_content` only absent or exactly null in visible mode;
- preserve whether optional `id`, `content`, and `encrypted_content` were absent or
  present/null, and preserve every accepted visible part semantically and in order;
- count visible summary/content bytes and material bytes through existing request and
  quota/accounting bounds;
- do not create a reasoning replay-lookup candidate when no provider reasoning ID or
  encrypted state exists. The full accepted item still participates in canonical
  request bytes, Local HMAC signing, request bounds, and accounting.

The dialect permits an empty visible structure, but it must be validated and
preserved—not stripped. The live acceptance target is the observed nonempty visible
state.

### Encrypted-state mode

Preserve the existing strict encrypted replay contract:

- a nonempty encrypted value requires the existing independent key/route capability;
- it requires a valid existing reasoning ID;
- ID-less or null-ID encrypted state is rejected as unobserved and unauthorized;
- visible content must not be mixed with encrypted state;
- encrypted item/request size caps, ownership lookup, replay, provider-state
  exclusion, and failure-before-provider behavior remain unchanged.

Reject ambiguous/mixed visible+encrypted shapes. Unexpected reasoning fields remain
fail-closed after the established removal of explicitly reviewed client-only internal
metadata.

## 4. Containment and invariants

Prove all of the following:

- `openai-default` still rejects a reasoning item lacking its required public ID;
- Codex 0.147 behavior is unchanged and strict;
- Codex 0.149 with a valid ID remains byte/value-equivalent after validation;
- absent-ID and explicit-null-ID 0.149 visible states are accepted without ID
  insertion;
- no other client spec opts into optional reasoning IDs;
- no arbitrary server pairing can select the 0.149 module; the reviewed Local pair is
  the only compatible application path;
- hosted-tool routes and adapter-managed search candidates receive no new authority;
- function-call/output adjacency, IDs, taxonomy, request bounds, Local route
  filtering, signed identity, nonce replay, session/key isolation, reservation,
  finalization, and PostgreSQL truth remain intact;
- accepted visible reasoning content is never logged, audited, persisted, placed in
  OAP artifacts, used as identity/route/tool authority, or exposed in error text.

Do not move routing, provider selection, public capability admission, quota logic, or
accounting authority into the client module.

## 5. Required pure, negative, integration, and documentation evidence

Before protected traffic, add and pass at minimum:

- source-fixture validation for exact tag/commit/paths/types and no-ID-generation
  behavior;
- default/OpenAI and 0.147 missing-ID rejection;
- 0.149 valid-ID unchanged;
- exact absent-ID and null-ID visible-state acceptance with unchanged synthetic
  nonempty content and empty summary;
- both exact Codex content part types and exact summary type;
- absent/null encrypted field in visible mode;
- no ID injected at normalization, policy, replay-candidate, upstream reconstruction,
  Local signing, or transport boundaries;
- malformed content/summary objects, extra fields, wrong types, unsupported variants,
  duplicate/mixed structures, invalid Unicode, per-part overflow, aggregate overflow,
  and excessive count rejection;
- ID-less encrypted, null-ID encrypted, empty encrypted, and mixed encrypted+visible
  rejection;
- unreviewed client/server pair rejection and exact Local pairing;
- unchanged function-call/output chronology and tool taxonomy;
- hosted search/MCP/provider authority negatives;
- replay ownership, signed identity, tamper, privacy, quota estimation, reservation,
  finalization, rollback, and upstream payload reconstruction regressions;
- the existing real-shape structural fixture plus the new synthetic source-derived
  reasoning fixture;
- normal fake two-turn, malformed reasoning fake, and pre-admission rejection
  accounting matrices.

Update only the affected compatibility/provider/accounting documentation. State that
optional reasoning ID is a pinned Codex rust-v0.149.0 client dialect fact, limited to
the reviewed Local pair, while ordinary OpenAI Responses still requires an ID. State
that visible reasoning is forwarded transiently and not stored by default. Do not
claim general Codex, OpenAI, Local, or release acceptance before the live gates.

Run full Ruff/format/compilation, focused module/policy/replay/route/signing/privacy/
accounting/verifier tests, the relevant PostgreSQL tests, normal and negative fake
two-turn runs, diff/scope/source checks, and all ten PR checks on the exact diagnostic
implementation head before protected traffic.

## 6. Qualification accounting correction

Correct only the verifier expectation. A Gateway request rejected before admission
and reservation must not be required to create a reservation or ledger row. For the
known failed g2/l1/q1 topology, one finalized admitted row with zero pending is valid
failed-run accounting.

Derive expected terminal rows from requests actually admitted/reserved, not raw
Gateway request count. Require every reservation that exists to be terminal; require
ledger/reservation state coherence and zero pending. Do not insert dummy/failure rows,
change Gateway accounting semantics, hide a released/failed/held row, or call a
pre-admission rejection successful.

For successful two-turn qualification, both admitted requests must have terminal
accounting results and zero pending. Add tests for pre-admission rejection, failure
after reservation, one-turn success, two-turn success, contradictory/missing rows,
and zero-pending enforcement.

## 7. One protected diagnostic acceptance

On the exact clean diagnostic implementation head with all ten checks green, execute
exactly one zero-retry protected process:

real task-local Codex 0.149.0 -> Gateway -> unchanged Local Coding at
`4d3ab2f...` -> unchanged protected Qwen.

Do not alter prompt, tools, model, route, Local configuration, or Qwen to steer the
result. Direct bounded stdout only; no prohibited-value redirection or retention.

Acceptance requires:

- turn 1 reaches Local/Qwen once, returns valid 2xx SSE, and closes normally;
- Codex naturally issues one function-result continuation;
- Gateway selects the exact 0.149/Local pair and accepts the state-bearing ID-less
  reasoning item under the new spec;
- the accepted item retains its nonempty visible content and absent ID; no ID is
  manufactured at any boundary;
- turn 2 reaches Local and Qwen once under the intended topology;
- function-call/output chronology remains valid;
- the final assistant/message lifecycle completes normally;
- no Gateway 4xx/stream validator error or Gateway-induced Local disconnect;
- valid terminal usage; terminal accounting for both admitted requests; zero pending;
- signed identity, replay/idempotency/tamper/session isolation, hosted-search denial,
  route containment, privacy, and post-health gates remain green.

If Local or Qwen rejects the correctly preserved ID-less visible state, publish the
exact bounded boundary evidence and stop. Do not modify Local or Qwen. Any other
failure also stops without retry or hook-free final.

## 8. Remove temporary diagnostics and run one hook-free final

Only if section 7 passes completely:

1. remove every temporary 155-ad/155-ae qualification hook and diagnostic-only
   production hook not part of the permanent reviewed client-policy contract,
   including the `SLAIF_155X_*` product hook/writer and dependent temporary modes;
2. retain the permanent spec/validator, strict regressions, canonical source fixture,
   ordinary fake verifier, and permanent hook-free `--tool-roundtrip-protected`
   runner;
3. prove hook/artifact/raw-value sink absence with AST/source checks outside immutable
   OAP history;
4. run full affected pure/fake/PostgreSQL tests, Ruff/format/compile, privacy/scope
   checks, and require all ten PR checks on the exact final hook-free implementation
   head;
5. run exactly one fresh zero-retry hook-free protected two-turn qualification against
   that exact head with the same section-7 acceptance criteria.

Only this hook-free run can establish Gateway acceptance. Do not retry a failed final.

## Privacy and cleanup

Retain no real reasoning text, prompts, request/response bodies, tool names/content,
IDs, credentials, endpoints, raw headers/SSE, body/signature digests, canonical bytes,
nonce/timestamp values, arbitrary exceptions/errors, or temporary paths. Live
visible reasoning may exist only transiently in the request/transport path. Evidence
uses structural classes, booleans, counts, and synthetic test text only.

At terminal closure remove the private runtime reference and all 155-ae task roots,
installed Codex files, diagnostic artifacts, processes, listeners, containers,
databases, bytecode, and temporary state. Preserve unrelated state and both worktrees.

## Allowed paths

    app/slaif_gateway/modules/contracts.py
    app/slaif_gateway/modules/clients/codex_0149.py
    app/slaif_gateway/modules/clients/codex_support.py
    app/slaif_gateway/services/responses_request_policy.py
    app/slaif_gateway/services/responses_gateway.py
    scripts/capture_codex_protocol.py
    scripts/verify_local_coding_full_stack.py
    tests/fixtures/codex/0.149.0/responses-reasoning-dialect-v1.json
    tests/unit/test_codex_protocol_capture.py
    tests/unit/test_codex_client_modules.py
    tests/unit/test_responses_request_policy.py
    tests/unit/test_responses_codex_multiturn_replay.py
    tests/unit/test_responses_codex_streaming_tools.py
    tests/unit/test_upstream_payload_reconstruction.py
    tests/unit/test_v1_responses_quota.py
    tests/unit/test_local_coding_full_stack_verifier.py
    tests/unit/test_oap_governance.py
    tests/e2e/test_openai_python_client_responses.py
    docs/provider-forwarding-contract.md
    docs/responses-compatibility.md
    docs/compatibility-matrix.md
    docs/accounting.md
    oap/active
    oap/orders/155-ae-codex-0149-idless-visible-reasoning-and-final-acceptance.md
    oap/reports/155-ae-codex-0149-idless-visible-reasoning-and-final-acceptance.md

`responses_gateway.py` may change only to remove temporary qualification machinery
after successful diagnostic acceptance. No server module/registry change, schema,
migration, dependency, lockfile, Local/Qwen/Codex product change, broad refactor,
previous order/report edit, AGENTS/OAP protocol change, merge, auto-merge, release,
or next continuation is authorized.

## Immutable report, handoff, and response contract

Before creating the report, assert no `oap/reports/155-ae-*` path exists. Publish one
report exactly once as a report-only `SELF` commit whose first parent is the final
implementation head. Never amend, rewrite, format, replace, or recommit it after
publication, including after compaction, restart, CI waiting, or wording review. On
resume with an existing report, reconcile read-only only.

`RESULT=PASSED` requires the section-7 diagnostic acceptance, complete temporary-hook
removal, and the fresh section-8 hook-free protected acceptance. Otherwise publish
`RESULT=FAILED` with the narrowest privacy-safe boundary and stop.

Record source tag/commit/paths, source-fixture digest, module/spec version, exact
containment, positive/negative/security/privacy/replay/accounting evidence, diagnostic
and hook-free run counts, live topology/usage/close/accounting, hook absence, cleanup,
implementation/report topology, and all checks. Do not merge or activate 155-af.

On pass only, post the exact hook-free implementation and immutable report heads to
Local Coding PR #7 so Local strategy can resume its prepared Objective-005 acceptance
matrix. Require all ten checks on the immutable report head, send exactly two response
FIFO bytes `OK` once, return to one blocked control-FIFO read, and stop.
