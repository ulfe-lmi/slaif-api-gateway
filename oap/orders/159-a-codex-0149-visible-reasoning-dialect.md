# OAP Work Order — 159-a

## Objective and business reason

Create the fourth clean post-Objective-155 decomposition PR from merged
Objective-158 main. Reconstruct the accepted Codex-0.149 visible-reasoning
request dialect and the correction that treats `encrypted_content: null` as
visible state rather than encrypted replay.

This objective owns only version-scoped reasoning request semantics. It must
not add ID-less function/custom tool-call admission, call-ID-HMAC replay,
second-turn function-output request chronology, replay repository/service
changes, or final protected acceptance assigned to Objective 160.

## Verified starting state

- Repository: `ulfe-lmi/slaif-api-gateway`.
- Remote `main` is merged Objective-158 commit
  `f1128c2d3cd8f81f2986a1bb5c0f5904c3372c4c`.
- Objective 158 PR #295 is merged; implementation head is
  `a72d9074952d00e70c3a45552f43c6eb632c3da9`, immutable PASSED report head is
  `6214f321469289aca58c364845516577f05154ad`.
- Main contains doctrine adoption, the Codex-0.149 structural/session client,
  exact Local server/pair/identity/transport, and pair-local response-stream
  state machines. The second-turn visible reasoning request remains rejected.
- Objective 155 remains permanently closed. PR #291 remains untouched at
  report head `45eeeb538e95ab3ae1d4d6e78ffb654e0e496fa2`; accepted final
  implementation is `acea2af4ca0f4586fc159c91607e1848f53f1107`.
- Use Objective-155 null-encrypted implementation head
  `34ab5afd09af026286779838db21cddad1717877` as the read-only pre-ID-less-tool
  source. Exact target blobs are listed below.
- Exact Codex source authority is OpenAI Codex tag `rust-v0.149.0`, commit
  `758ef40f50c1a458425c7cfbf1eb12cbc07af0b0`.
- No Objective-159 branch or PR exists at activation.

## PR contract

- PR mode: `CREATE_NEW_PR`
- Base: `main` at `f1128c2d3cd8f81f2986a1bb5c0f5904c3372c4c`
- Branch: `oap/159-codex-0149-visible-reasoning-dialect`
- Title: `obj159: reconstruct Codex 0.149 visible reasoning dialect`
- Create exactly one PR for Objective 159.
- Do not merge or enable auto-merge.
- Preserve PR #291 and all prior objective history.
- If main moves, retain the exact base and report it; do not silently absorb
  unrelated changes.

Use a new clean isolated worktree and preserve all unrelated state. Commit the
exact activated order and selector unchanged.

## Required reading

Read completely before editing:

- current `AGENTS.md` and `AGENTIC_CLIENT_INTEGRATION.md`, especially absent/
  null/value, reasoning, identity, replay, testing, and decomposition rules;
- `OAP-COMMUNICATION-coding-agent.md`;
- current merged client policy/spec, request policy, stream validator, Local
  pair, and affected tests/docs;
- exact Codex rust-v0.149.0 source types and request preparation at commit
  `758ef40...`;
- the pre-ID-less-tool source at `34ab5afd...` and accepted final source only
  to distinguish later Objective-160 changes;
- immutable Objective-155 155-ae and 155-af reports as historical evidence.

## Allowed paths

Production/client contract:

- `app/slaif_gateway/modules/contracts.py`
- `app/slaif_gateway/modules/clients/codex_0149.py`
- `app/slaif_gateway/services/responses_request_policy.py`

Permanent capture/fixture/tests:

- `scripts/capture_codex_protocol.py`
- `tests/fixtures/codex/0.149.0/responses-reasoning-dialect-v1.json`
- `tests/unit/test_codex_client_modules.py`
- `tests/unit/test_responses_codex_multiturn_replay.py`

Permanent documentation:

- `docs/accounting.md`
- `docs/compatibility-matrix.md`
- `docs/module-architecture.md`
- `docs/responses-compatibility.md`
- `docs/security-model.md`

OAP transcript:

- `oap/active`
- `oap/orders/159-a-codex-0149-visible-reasoning-dialect.md`
- `oap/reports/159-a-codex-0149-visible-reasoning-dialect.md`

No other path is authorized. In particular, `responses_gateway.py`, production
streaming, Local module/identity, replay repository/service, schema/migrations,
E2E, full-stack verifier, Local Coding, and Qwen are read-only.

## Exact target blobs

Reconstruct these exact pre-ID-less-tool blobs from `34ab5afd...`:

| Path | Required blob |
|---|---|
| `app/slaif_gateway/modules/contracts.py` | `3accb526ee519d1b78cf85bc22274e8de155afff` |
| `app/slaif_gateway/modules/clients/codex_0149.py` | `bee1f18c0e61726b1046fa965e5a3edf42b8a085` |
| `scripts/capture_codex_protocol.py` | `4aa54548065f457b2afa1cc939c02254cc72ae58` |
| `tests/fixtures/codex/0.149.0/responses-reasoning-dialect-v1.json` | `5b90402eb3fd1a968fd5ab54774bcaf0575f3c9c` |
| `tests/unit/test_codex_client_modules.py` | `4f0a8ab5bbe9a00521ffa2718c17be8e7e498923` |
| `tests/unit/test_responses_codex_multiturn_replay.py` | `d5395e0f263a35e4d3b8b44a61608a320f53a13b` |

Do not copy the whole request-policy blob from that source because it also
contains historical top-level continuation work assigned to Objective 160.
Apply only the reasoning/null semantics below to current main.

## Source facts to prove

Before relying on the compatibility, prove from exact Codex source and the
synthetic permanent fixture that:

- `ResponseItem::Reasoning.id` is optional in rust-v0.149.0;
- reasoning carries `summary`, optional visible `content`, and optional
  `encrypted_content`;
- the request input is a vector of ResponseItem values;
- the normal request-preparation path does not manufacture a reasoning ID;
- visible reasoning content supports only the exact bounded text-item types
  represented by the source-derived contract;
- ordinary public OpenAI reasoning replay still requires an ID, so this is a
  Codex-0.149 client dialect delta, not a global Responses relaxation.

No real reasoning text, IDs, prompts, outputs, arguments, or client capture
values may enter the fixture or report.

## Required production behavior

### Declarative client ownership

Represent the dialect only through `ResponsesClientPolicySpec` facts with
strict defaults for every other client:

- visible reasoning item ID optionality;
- exact visible content fields/types;
- maximum visible part count;
- maximum per-part bytes;
- maximum aggregate visible bytes;
- explicit denial of ID-less encrypted reasoning.

Enable those facts only on exact `codex-0.149-responses-v1`. Pair/runtime
containment must continue to require the already-reviewed Local server path
and existing request-envelope authority. OpenAI default, Codex 0.147, arbitrary
clients, servers, and hosted routes remain strict.

### Visible reasoning validation

For the exact authorized dialect:

- accept `type == "reasoning"` with a valid existing ID, explicit null ID, or
  absent ID as the source contract permits;
- never synthesize, hash-generate, UUID-generate, positional-generate,
  reconstruct, or otherwise fabricate an ID;
- require `summary` to be a bounded array of exact summary-text objects with
  exact fields and valid bounded Unicode text;
- allow visible `content` only as null/absent or a bounded array of exact
  source-supported text parts with exact fields/types and valid bounded text;
- enforce accepted maxima: at most 64 visible parts, 8,192 bytes per visible
  part, 65,536 aggregate visible bytes, and the existing 64-part/65,536-byte
  summary bounds;
- preserve valid IDs, absence/null state, summary, visible content, newlines,
  tabs, Unicode, and ordering semantically unchanged;
- permit `encrypted_content` only absent or explicitly null on this visible
  path;
- reject extra fields, malformed types, invalid Unicode, excessive parts/
  bytes, unsupported content types, mixed state, and any non-null encrypted
  value without its existing independent encrypted-replay capability and
  ordinary valid provider reasoning ID.

### Null encrypted detector

Correct/retain the early capability detector so:

- field absent -> not encrypted replay;
- `encrypted_content: null` -> not encrypted replay;
- non-null encrypted value -> existing encrypted-replay capability path;
- malformed non-null state never obtains the visible exception;
- visible plus non-null encrypted state and ID-less encrypted state remain
  prohibited.

Add an application-level `ResponsesRequestPolicy.apply()` regression showing
the exact synthetic visible/no-ID/null-encrypted shape reaches and passes the
visible validator without an encrypted-replay grant. Prove non-null encrypted
state still hits the independent capability boundary.

### Replay, accounting, and privacy containment

- ID-less visible reasoning does not create a replay-reference candidate and
  grants no replay ownership by itself.
- Do not change signed identity, nonce/replay, function-call/output chronology,
  route/tool authority, quota, accounting, or provider forwarding.
- Visible reasoning bytes remain ordinary bounded model input for estimation;
  text/IDs are never stored in ledgers, audits, logs, metrics, exports, errors,
  or OAP evidence.
- A pre-admission rejection creates no dummy reservation/ledger row.

## Required negative and regression tests

The exact target test blobs plus focused request-policy tests must prove:

- default OpenAI and Codex 0.147 reasoning without required ID reject;
- exact Codex 0.149 valid-ID reasoning accepts unchanged;
- absent/null ID with valid nonempty visible content accepts without ID
  injection;
- empty summary and nonempty visible content are treated as state-bearing, not
  as an empty placeholder;
- visible content survives normalization semantically unchanged, including
  newlines/tabs and every supported part type;
- malformed/extra/unsupported parts, summaries, field types, IDs, Unicode,
  mixed state, part counts, per-part bytes, and aggregate bytes fail closed;
- absent/null encrypted content stays visible; non-null encrypted content
  requires its existing capability and valid ID;
- arbitrary client/server pairs cannot acquire this delta;
- function-call/output chronology, tool taxonomy, hosted-search denial,
  signed identity, stream behavior, quota, and accounting remain unchanged;
- the permanent source/fixture is canonical, privacy-safe, and pinned to exact
  rust-v0.149.0 commit authority.

Do not add ID-less function/custom tool-call success tests in this objective.

## Required verification

Use focused evidence only:

1. Run complete changed unit files:
   - `tests/unit/test_codex_client_modules.py`
   - `tests/unit/test_responses_codex_multiturn_replay.py`
2. Run focused existing request-policy, encrypted-reasoning, replay-candidate,
   tool-authority, and default/Codex-0.147 regression tests affected by the
   dialect.
3. Validate the reasoning dialect fixture and exact source/provenance contract
   using the permanent capture tool. No real client/provider request is needed.
4. Run repository Ruff check, Python compilation, and `git diff --check`.
5. Verify all six exact target blobs.
6. Mechanically inspect the request-policy diff: it may contain only visible
   reasoning validation, bounds/accounting inclusion, and null encrypted
   detection. It must contain no optional tool-call ID, call-ID fallback,
   second-turn chronology, replay lookup/storage, or Objective-155 diagnostic.
7. Prove no diff to non-allowed app paths, Gateway stream wiring, Local module,
   replay repository/service, schema/migrations, E2E, doctrine, Local, or Qwen.
8. Push implementation, create the unique PR, and require all ten normal
   GitHub checks successful on the exact final report head.

No required evidence may be skipped, xfailed, pending, cancelled, missing, or
environment-blocked.

## Documentation

Update only allowed permanent docs to state:

- the exact rust-v0.149.0 visible-reasoning dialect and pair containment;
- optional visible reasoning ID without fabrication;
- exact content/summary/null-encrypted bounds and failure law;
- ordinary/default/0.147 and ID-less encrypted state remain strict;
- transient no-content-retention and ordinary input accounting;
- this layer is pure/source-derived regression evidence, not successful
  second-turn or protected qualification.

Preserve doctrine links and remove/avoid Objective-155 verifier/runtime/PR-head
prose. Do not claim ID-less tool-call replay or final acceptance.

## Explicit non-goals

Do not:

- implement Objective 160;
- modify replay repository/service or database schema;
- permit absent/null function/custom tool-call item IDs;
- add call-ID-HMAC ownership fallback or second-turn function-output admission;
- change response-stream, Local transport/identity, Gateway orchestration,
  provider, accounting, routing, or tool authority;
- strip a reasoning item as a placeholder or fabricate identity;
- generalize the delta to OpenAI/default/0.147/arbitrary clients;
- modify Local Coding, Qwen, PR #291, or inherited doctrine;
- run protected/real provider traffic;
- merge or auto-merge;
- claim final clean-stack/release/deployment/production acceptance.

## Setup and cleanup

Routine task-local dependencies and pure/source-derived fixture checks are
authorized. No protected credentials, Local service, Qwen, provider, or
production data may be used. Clean only uniquely created resources and report
their absence.

## Immutable report

Publish exactly:

`oap/reports/159-a-codex-0149-visible-reasoning-dialect.md`

The report must include:

- `RESULT=PASSED` or `RESULT=FAILED`;
- exact repository/base/branch/PR/head/no-auto-merge state;
- implementation head and `Report publication commit: SELF`;
- report-only topology and complete changed-path/app inventory;
- exact six blob targets and actual blobs;
- exact rust source/fixture authority facts;
- declarative spec containment and visible/null validator behavior;
- positive/negative/default/0.147/request-policy test mapping and counts;
- mechanical absence of tool-ID/call-ID/replay/second-turn/diagnostic changes;
- lint/compile/diff/privacy/accounting evidence;
- all ten final report-head check states;
- cleanup, documentation impact, and limitations.

Commit implementation, then a report-only commit whose first parent is the
implementation head and only changed path is the report. Verify it is the
remote PR head and all claims exist, write exactly `OK` to the response FIFO,
then return to one blocking control-FIFO read.
