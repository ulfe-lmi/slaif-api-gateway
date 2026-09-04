# OAP Work Order — 160-a

## Objective and business reason

Create the fifth and final clean post-Objective-155 decomposition PR from
merged Objective-159 main. Reconstruct the accepted Codex-0.149 ID-less
function/custom tool-call continuation and call-ID-HMAC replay ownership,
complete permanent regression tooling, and prove the entire clean `app/` tree
is mechanically identical to accepted Objective-155 implementation
`acea2af4...`.

This objective completes accepted-behavior reconstruction only. It is not the
later generic Responses/transport refactor and does not authorize new client,
provider, Local, Qwen, tool, identity, replay, accounting, or routing behavior.

## Verified starting state

- Repository: `ulfe-lmi/slaif-api-gateway`.
- Remote `main` is merged Objective-159 commit
  `07ae3cce21c52654bdec1f50bc7e5da9c59082c6`.
- Objective 159 PR #296 is merged; implementation head is
  `3d782a6f0e739dbcbf0cf20ef024035844dc530f`, immutable PASSED report head is
  `caad47d969875edc572e4ad8594110094ebba60c`.
- Main contains doctrine adoption, exact Codex structural/session and visible
  reasoning dialects, Local server/pair/final identity, and exact response
  stream state machines. The remaining `app/` delta to accepted implementation
  is exactly the six paths listed below.
- Objective 155 is permanently closed. PR #291 remains immutable at accepted
  report head `45eeeb538e95ab3ae1d4d6e78ffb654e0e496fa2`; accepted implementation head is
  `acea2af4ca0f4586fc159c91607e1848f53f1107`; accepted `app/` tree is
  `bd536a282362cc549cc0c5518db8e743af667b63`.
- Exact Codex source authority remains tag `rust-v0.149.0`, commit
  `758ef40f50c1a458425c7cfbf1eb12cbc07af0b0`.
- Exact unchanged Local Coding consumer authority remains
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`; do not modify or run its protected
  stack in this objective.
- No Objective-160 branch or PR exists at activation.

## PR contract

- PR mode: `CREATE_NEW_PR`
- Base: `main` at `07ae3cce21c52654bdec1f50bc7e5da9c59082c6`
- Branch: `oap/160-idless-tool-replay-clean-stack`
- Title: `obj160: reconstruct ID-less tool replay and close clean stack`
- Create exactly one PR for Objective 160.
- Do not merge or enable auto-merge.
- Do not modify, close, rewrite, squash, force-push, or merge PR #291.
- If remote main moves, retain the exact authorized base and report it; do not
  silently absorb unrelated changes.

Use a new isolated clean worktree. Preserve all unrelated worktrees/artifacts.
Commit this exact order and selector unchanged.

## Required reading

Read completely before editing:

- current `AGENTS.md` and `AGENTIC_CLIENT_INTEGRATION.md`, especially tool-call
  identity, replay ownership, no-downgrade, rotation, accounting, exact-client
  fake conformance, decomposition, and cleanup rules;
- `OAP-COMMUNICATION-coding-agent.md`;
- merged Objective-156 through 159 reports and current implementation;
- exact final six production files and permanent tests at `acea2af4...`;
- exact Codex rust-v0.149.0 function/custom call/output types and
  `ModelClient::prepare_response_items_for_request()` at `758ef40...`;
- current replay schema/migration/repository constraints and documentation;
- the deterministic fake two-turn core in historical
  `scripts/verify_local_coding_full_stack.py` only as read-only extraction
  source. Do not copy its OAP/protected/diagnostic architecture.

## Allowed paths

Final production convergence:

- `app/slaif_gateway/db/repositories/codex_replay.py`
- `app/slaif_gateway/modules/clients/codex_0149.py`
- `app/slaif_gateway/modules/contracts.py`
- `app/slaif_gateway/services/codex_replay_service.py`
- `app/slaif_gateway/services/responses_gateway.py`
- `app/slaif_gateway/services/responses_request_policy.py`

Permanent tests:

- `tests/integration/test_codex_replay_references_postgres.py`
- `tests/unit/test_codex_client_modules.py`
- `tests/unit/test_codex_replay_service.py`
- `tests/unit/test_responses_codex_multiturn_replay.py`
- `tests/unit/test_responses_codex_streaming_tools.py`
- `tests/e2e/test_openai_python_client_responses.py`

Permanent compact verifier extraction:

- `scripts/verify_codex_0149_local_roundtrip.py`
- `tests/unit/test_codex_0149_local_roundtrip.py`

Permanent documentation:

- `docs/accounting.md`
- `docs/compatibility-matrix.md`
- `docs/module-architecture.md`
- `docs/provider-forwarding-contract.md`
- `docs/responses-compatibility.md`
- `docs/security-model.md`

OAP transcript:

- `oap/active`
- `oap/orders/160-a-idless-tool-replay-and-clean-stack-closure.md`
- `oap/reports/160-a-idless-tool-replay-and-clean-stack-closure.md`

No other path is authorized. In particular, schema/migrations, Local module/
identity, production stream validator, capture/fixtures, inherited doctrine,
Objective-155 verifier/tests/governance, Local Coding, and Qwen are read-only.

## Exact final production and permanent test targets

Reconstruct these exact accepted blobs from `acea2af4...`:

| Path | Required blob |
|---|---|
| `app/slaif_gateway/db/repositories/codex_replay.py` | `2e5ddd592c3a3f39ffef789c442dba884444919c` |
| `app/slaif_gateway/modules/clients/codex_0149.py` | `9f773ea74f9aeb7e6ed651f34fc85466fbbd7a4d` |
| `app/slaif_gateway/modules/contracts.py` | `b24a19901445483d18c6799b55e89fb73d1fa73f` |
| `app/slaif_gateway/services/codex_replay_service.py` | `c0813d120c67474785bb1ddad971dd2cd4dcdec6` |
| `app/slaif_gateway/services/responses_gateway.py` | `c280af6354904ebcb831f75023373b1fecfdb700` |
| `app/slaif_gateway/services/responses_request_policy.py` | `e2197a3184ee028f95e0a72dbe8857954cad45bd` |
| `tests/integration/test_codex_replay_references_postgres.py` | `7810a949e00b7c89c290ba79ac246fa145d5c651` |
| `tests/unit/test_codex_client_modules.py` | `ba14d1e8a9953cdc885918c1fa867cf23deba630` |
| `tests/unit/test_codex_replay_service.py` | `29a9b11195670f933d83ffef4f23673e92801893` |
| `tests/unit/test_responses_codex_multiturn_replay.py` | `f91038cf946aeb097b6de91886bcd21490115e47` |
| `tests/unit/test_responses_codex_streaming_tools.py` | `f872fa53820687a3a6612c8131d4fddb73521757` |

`tests/e2e/test_openai_python_client_responses.py` must remain at its already
accepted exact blob `aa95589294f48f883b1c174a5a3a43428d9c44f0` unless the
new compact verifier requires no change there; prefer no change.

No Objective-155 qualification hook is present in the exact final
`responses_gateway.py`; do not reintroduce one.

## Source hypothesis and client-dialect rule

Prove from exact Codex source before relying on the behavior:

- function-call and custom-tool-call item IDs are optional while `call_id` is
  mandatory;
- matching outputs may omit item ID and bind through `call_id`;
- request preparation removes an existing non-prefixed item ID immediately
  before the provider request and does not create a replacement;
- therefore a non-first-party provider's tool-call item ID is not guaranteed
  to survive Codex response-to-continuation serialization, while `call_id`
  remains the invocation contract.

Architectural rule: on exact Codex 0.149 and the reviewed Local pair, an absent
tool-call item ID is valid only when the call is authenticated as prior
same-key provider output through the existing call-ID HMAC. Never invent an ID
and never skip replay ownership. This is not a global OpenAI relaxation.

## Required production behavior

### Declarative client policy

Add strict-default client-spec facts for:

- optional function-call item ID;
- optional custom-tool-call item ID;
- permission for ID-less tool continuation to use authenticated call-ID replay.

Enable them only for exact `codex-0.149-responses-v1` through the reviewed
`local-coding-v1` pairing/capability path. OpenAI default, Codex 0.147,
arbitrary clients/servers, hosted routes, reasoning, and compaction do not
inherit them.

### Request chronology and shape

For the exact policy:

- permit function/custom tool-call item `id` absent or null and preserve that
  state; never generate, infer, hash, UUID, positionally reconstruct, or copy an
  ID;
- if an item ID is present, validate it exactly as before;
- continue requiring bounded valid `call_id`, exact approved tool taxonomy,
  name/namespace/status, bounded arguments/input, call-ID uniqueness, and the
  exact adjacent matching function/custom output;
- permit the matching output item ID to be absent where the exact dialect does;
- bind call and output by exact `call_id`;
- reject malformed, oversized, duplicate, reordered, smuggled, unauthorized,
  unbounded, mismatched, or output-without-call variants before quota/provider
  work.

### Replay ownership and no-downgrade

Reuse existing `codex_replay_references` HMAC-only design and schema. Do not
add a migration or persist raw identifiers.

When item ID is present:

- retain item-ID-HMAC lookup;
- also require persisted call-ID HMAC match for function/custom calls;
- never fall back to call-ID-only lookup if the supplied item ID is wrong,
  unknown, malformed, expired, or mismatched.

When item ID is absent/null and exact client policy authorizes fallback:

- compute bounded call-ID HMAC candidates under configured active/retained
  versions;
- query only same-key, same-kind, active unexpired rows by call digest;
- require exactly one row;
- verify stored HMAC version, call digest, item kind, tool namespace/name, and
  all content-free binding facts;
- enforce the same provider/route/upstream-model compatibility as ordinary
  replay before provider side effects.

Unknown, ambiguous, duplicate, expired, cross-key, cross-route, wrong-provider,
wrong-model, wrong-tool, malformed-call-ID, or unavailable-HMAC cases fail
closed. Reasoning/compaction do not gain call-ID fallback; ID-less visible
reasoning remains its separate no-replay path.

### Gateway ordering, accounting, and privacy

- Defer ID-less replay verification only until authenticated Local server
  context is available; complete same-key/route/provider/model verification
  before reservation/provider work.
- Persist replay references only after successful usage-backed accounting as
  the existing contract requires; terminal completion remains held until
  persistence succeeds.
- Each admitted first/second model request has its own coherent PostgreSQL
  reservation and terminal ledger row; pre-admission rejection creates none;
  every failure leaves zero pending state.
- Raw item IDs, call IDs, HMAC digests, tool values, reasoning, prompts,
  results, signatures, credentials, and bodies must not enter logs, metrics,
  audits, exports, errors, reports, or durable verifier output.

## Required replay/security tests

Exact accepted tests must cover:

- 0.149 ID-less function and supported custom tool call with known matching
  call-ID reference succeeds;
- present correct item ID + call ID succeeds unchanged;
- present wrong item ID + correct call ID fails with no downgrade;
- unknown/expired/duplicate/ambiguous call ID fails;
- cross-key/route/provider/model/tool and namespace/name mismatch fail;
- malformed/oversized call IDs and call/output mismatch fail;
- output without prior approved call fails;
- default OpenAI and Codex 0.147 remain strict;
- existing item-ID uniqueness plus call-ID unique/index contract remains;
- HMAC rotation: old v1 present/itemless references work while v1 material is
  retained after v2 activation; new v2 present and ID-less function/custom
  references work; missing old material/version mismatch/ambiguous cross-
  version rows fail closed;
- raw values/digests/privacy canaries never enter evidence.

Execute the PostgreSQL replay integration test; collection or skip is not a
pass. Also run existing context/accounting, provider-failure, validator-failure,
quota, stream, identity, Local-pair, and hosted-tool-denial regressions affected
by final Gateway ordering.

## Permanent compact exact-client fake verifier

Create `scripts/verify_codex_0149_local_roundtrip.py` by extracting only the
durable fake two-turn core from the historical Objective-155 verifier. It must
be a normal, bounded, privacy-safe regression tool—not an OAP evidence system.

Required properties:

- install/accept and verify an exact task-local `@openai/codex@0.149.0` binary;
- use numeric loopback only, zero retries, temporary directories, and a
  repository-standard disposable PostgreSQL database;
- start the real Gateway candidate and one tightly bounded fake Local endpoint;
- never source protected credentials, contact Qwen/provider/Local product
  services, inspect GitHub/OAP/report topology, or use historical runtime
  references;
- return a first valid reasoning/function stream containing a syntactically
  valid non-Codex-prefixed tool-call item ID and bounded valid call ID so the
  actual client naturally serializes its second request;
- prove actual Codex removes/omits the item ID, preserves call ID, sends the
  adjacent matching output, and that Gateway authenticates/forwards turn 2;
- return a final assistant-message stream;
- prove exactly two Gateway admissions, two fake-Local requests, two finalized
  reservations, two finalized ledgers, zero pending, signed-header/body
  verification, no public bearer forwarding, no hosted authority, and normal
  client exit;
- emit only one fixed success line such as
  `VERIFY_CODEX_0149_LOCAL_ROUNDTRIP_OK turns=2 accounting_rows=2` or one fixed
  safe failure class;
- retain no request/response bodies, prompts, reasoning, IDs, call IDs, tool
  values, headers, credentials, endpoints, digests, arbitrary errors, or temp
  paths;
- clean all uniquely created processes, database state, installs, and files.

Add `tests/unit/test_codex_0149_local_roundtrip.py` covering its fixed fake
wire/state machine, exact binary provenance, two-request requirement,
privacy-safe output, retry denial, accounting predicate, malformed sequences,
and cleanup. Do not reproduce Objective-specific boundary snapshots,
qualification artifacts, protected relays, GitHub checks, report manifests,
suffix logic, or 0.148 differential machinery.

Run the compact verifier once locally with exact task-local Codex 0.149.0 and
fake loopback dependencies. This is not a protected/provider run.

## Final mechanical equivalence gates

Before report publication, require:

```text
git rev-parse <implementation-head>:app
  == bd536a282362cc549cc0c5518db8e743af667b63

git diff --exit-code \
  acea2af4ca0f4586fc159c91607e1848f53f1107 \
  <implementation-head> -- app/
```

Also require exact blob equality for all five permanent protocol fixtures:

- reasoning dialect: `5b90402eb3fd1a968fd5ab54774bcaf0575f3c9c`
- session relationship: `a0073a638b82750b3752ac5b78f5df91f97d7d56`
- structural v2: `c182dd195312368d58c80f25c915e83e8474a470`
- Local tool filter: `cdd33cb5c52377f80282803f53005074df091fc8`
- signed identity v1: `e1e4c43e10318ff3170859876dc4d8f6f7d5bdb9`

Require source/AST/diff gates proving:

- no `SLAIF_155X_` or qualification writer under `app/`;
- no `scripts/verify_local_coding_full_stack.py`;
- no `tests/unit/test_local_coding_full_stack_verifier.py`;
- no Objective-155 delta to `tests/unit/test_oap_governance.py`;
- inherited `AGENTIC_CLIENT_INTEGRATION.md` unchanged;
- permanent doctrine links remain;
- no raw-value/evidence sink in the compact verifier;
- every accepted client/server/security/accounting behavior has a mapped
  permanent test or exact fixture.

Build a machine-readable/test-generated obligation manifest with `missing=[]`
covering the final app blobs, five fixtures, replay/no-downgrade/rotation,
identity, stream, exact-client fake two-turn, PostgreSQL accounting, privacy,
and historical-machinery absence. This manifest is permanent regression logic,
not an OAP-specific report parser.

## Required verification

This is the final clean-stack phase gate. Run:

1. Complete changed unit files and compact-verifier unit file.
2. Executed PostgreSQL replay-reference and relevant context/accounting tests,
   with no required skip/xfail/failure.
3. Existing affected mocked official-client E2E and Local-pair accounting tests.
4. Exact task-local Codex 0.149 compact fake two-turn verifier once, zero retry.
5. Provider-failure, validator-failure, replay/tamper, quota rollback, hosted-
   authority denial, identity, and stream regression selections.
6. Repository Ruff check, Python compilation, `git diff --check`, privacy/
   source/AST/scope gates, exact blob checks, and final `app/` tree equivalence.
7. All ten normal GitHub checks on the exact final report head.

No required test may be skipped, xfailed, pending, cancelled, missing, silently
replaced, or environment-blocked. Do not require `ruff format --check` to
rewrite frozen accepted blobs; repository Ruff `check` remains mandatory.

## Documentation

Update allowed permanent docs to describe the final implemented clean stack:

- exact Codex-0.149/Local pair and source profile;
- optional tool item IDs only under the exact dialect;
- mandatory call ID and HMAC same-key replay ownership/no-downgrade/rotation;
- visible reasoning remains separate and ID-less encrypted state denied;
- pair/tool/hosted authority remains default-false and independently gated;
- replay persistence timing, ordinary per-request PostgreSQL accounting, and
  zero-pending failure law;
- raw IDs are not persisted, while versioned HMAC digests are private replay-
  control metadata, not billing truth;
- exact-client fake two-turn and historical protected Objective-155 acceptance
  are distinct; this clean head still requires resumed Local OAP-005 protected
  acceptance and is not release/production certification.

Preserve doctrine links. Exclude Objective-155 verifier internals, report-head
conditions, temporary runtime/protected credential details, PR #291 as a
product condition, or broad generic-client claims.

## Explicit non-goals and boundaries

Do not:

- add new product behavior beyond exact accepted `acea2af4` `app/` semantics;
- change Local Coding, Qwen, protected/provider configuration, schema, or
  migrations;
- make protected or real-provider calls;
- broaden OpenAI/default/0.147/arbitrary client/server behavior;
- weaken identity, replay, stream, tool authority, quota, or accounting;
- fabricate any item/reasoning identity;
- carry Objective-155 full-stack verifier or diagnostic tests into clean main;
- begin generic Responses/transport refactoring;
- modify PR #291;
- merge, auto-merge, cut over, release, or claim production/certification.

## Setup and cleanup

Routine task-local exact Codex 0.149 installation, numeric-loopback fake
services, and repository-standard disposable PostgreSQL are authorized. No
protected credential or non-loopback provider/Local/Qwen service is authorized.
Clean only uniquely created resources and report their absence.

## Immutable report and clean-head handoff data

Publish exactly:

`oap/reports/160-a-idless-tool-replay-and-clean-stack-closure.md`

It must include:

- `RESULT=PASSED` or `RESULT=FAILED`;
- exact repository/base/branch/PR/head/no-auto-merge state;
- literal clean implementation head `G_clean` and
  `Report publication commit: SELF`;
- report-only topology and complete changed-path/app inventory;
- six exact production and five exact permanent test blobs;
- final `app/` tree hash and zero diff from `acea2af4...`;
- five permanent fixture blob results;
- source-derived optional-ID/call-ID facts and exact containment;
- request chronology, replay ownership/no-downgrade/rotation, PostgreSQL,
  accounting, privacy, identity, stream, hosted-authority, and failure test
  mapping/counts;
- compact permanent verifier file/size/scope, unit results, exact Codex
  provenance, bounded two-turn success/failure output, and cleanup;
- permanent obligation manifest with `missing=[]`;
- explicit historical machinery absence;
- all ten exact final report-head check states;
- documentation impact and honest Local-OAP-005/release limitations.

The implementation commit identified as `G_clean` must contain all permanent
product/tests/docs/tooling and no report. Then publish one report-only commit
whose first parent is `G_clean` and only changed path is the report. Verify the
remote PR head and all claims, write exactly `OK` to the response FIFO, then
return to one blocking control-FIFO read.

Do not contact Local PR #7 yourself. After strategic acceptance/merge, the
strategic model will hand Local OAP-005 the literal `G_clean`, report head,
merged main, app-tree hash, and exact Local authority.
