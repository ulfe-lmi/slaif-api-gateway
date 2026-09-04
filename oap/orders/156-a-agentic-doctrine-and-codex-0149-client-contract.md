# OAP Work Order — 156-a

## Objective and business reason

Create the first clean post-Objective-155 decomposition PR from current
`main`. This PR has two inseparable, bounded purposes:

1. adopt and link the already-merged permanent agentic-client doctrine through
   the repository constitution and its permanent documentation; and
2. reconstruct the accepted Codex 0.149 structural/session client contract as
   a default-denied, non-authoritative client dialect.

This is accepted-behavior reconstruction, not new client support and not a
generic Responses/transport refactor. The result must be independently
merge-safe: because `local-coding-v1` is deliberately not reconstructed until
Objective 157, Codex 0.149 must still have no active server pairing and must
fail before quota/provider side effects when selected for runtime use.

## Verified starting state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Remote `main` is exactly
  `2823b1b8ca95aeb795b2df8bba49c2d9f2cb9ddf`, the merge commit for merged
  documentation-only PR #292.
- Relative to prior main
  `7ffce834915b74809109e8b579d8541cdcfa9df7`, that merge adds only root
  `AGENTIC_CLIENT_INTEGRATION.md`; `app/` is unchanged.
- The inherited doctrine is 3,060 lines, Git blob
  `7c48c679d14aa127f0c31fc3260e4a3fb01ee25f`, and SHA-256
  `1b498f8d15e11ff21639aa8981cc1fcc17b2581708e5d774d11f8955e38c74c8`.
- Objective 155 is technically accepted and permanently closed. Its immutable
  evidence branch is PR #291 at report head
  `45eeeb538e95ab3ae1d4d6e78ffb654e0e496fa2`; accepted implementation head is
  `acea2af4ca0f4586fc159c91607e1848f53f1107`. Do not modify that PR, branch,
  report, or history.
- Accepted Objective-155 `app/` tree target remains
  `bd536a282362cc549cc0c5518db8e743af667b63`; this first decomposition PR is
  intentionally only a partial step toward that final tree.
- The bounded pre-stream/pre-replay client-contract source snapshot is
  Objective-155 implementation commit
  `4eb768254fcde0a4108bcabb35f175a74bd07a3f`. Use it only as a read-only source
  for the exact paths and blobs named below; do not cherry-pick it because its
  ancestry also contains Local-Coding server behavior assigned to Objective
  157.
- No `oap/156-*` remote branch or PR exists at activation.
- Open unrelated Dependabot PRs #224 and #250 are out of scope.
- The primary checkout contains unrelated local/OAP state and linked
  worktrees. Preserve all of it; do not stash, reset, clean, delete, overwrite,
  or commit unrelated files.

## PR identity and branch contract

- PR mode: `CREATE_NEW_PR`
- Base branch: `main`
- Exact base SHA:
  `2823b1b8ca95aeb795b2df8bba49c2d9f2cb9ddf`
- Feature branch: `oap/156-agentic-doctrine-codex-0149-client-contract`
- PR title: `obj156: adopt agentic-client governance and reconstruct Codex 0.149 contract`
- Create exactly one PR for numeric Objective 156.
- Do not merge or enable auto-merge.
- Do not reuse, rebase, rewrite, close, or modify PR #291.
- If the remote base moves after work begins, keep this PR based on the exact
  authorized base and report the new state; do not silently absorb unrelated
  main changes.

Use a clean isolated linked worktree or another non-destructive workflow. Do
not switch/reset/clean the unrelated primary checkout or the Objective-155
worktree. Commit this activated order and `oap/active` unchanged on the new
objective branch as required by OAP.

## Required reading before editing

Read completely before implementation:

- the root `AGENTS.md` at the exact base;
- root `AGENTIC_CLIENT_INTEGRATION.md`, especially Parts I, II, IV, XIII, XV,
  XVIII, XIX, and XX;
- `OAP-COMMUNICATION-coding-agent.md`;
- `docs/module-architecture.md`;
- `docs/responses-compatibility.md`;
- `docs/compatibility-matrix.md`;
- `docs/security-model.md` and `docs/accounting.md` for the affected
  trust/privacy/accounting statements;
- current client-module contracts, registry, Codex 0.147 and 0.149 modules,
  Responses request policy, capture script, and affected tests on current
  main;
- the exact selected-path versions at read-only source commit `4eb768...`;
- the accepted Objective-155 report and final implementation only as evidence,
  never as a branch to amend or merge.

## Allowed paths

Product/client-contract reconstruction:

- `app/slaif_gateway/modules/contracts.py`
- `app/slaif_gateway/modules/clients/codex_0149.py`
- `app/slaif_gateway/services/responses_request_policy.py`

Permanent governance and documentation:

- `AGENTS.md`
- `docs/module-architecture.md`
- `docs/responses-compatibility.md`
- `docs/compatibility-matrix.md`
- `docs/security-model.md`
- `docs/accounting.md`

Permanent protocol tooling and fixtures:

- `scripts/capture_codex_protocol.py`
- `tests/fixtures/codex/0.149.0/responses-structural-v2.json`
- `tests/fixtures/codex/0.149.0/responses-session-relationship-v3.json`

Permanent tests:

- `tests/unit/test_agentic_client_integration_governance.py`
- `tests/unit/test_codex_client_modules.py`
- `tests/unit/test_codex_protocol_capture.py`
- `tests/unit/test_responses_request_policy.py`
- `tests/integration/test_codex_client_modules_postgres.py`

OAP transcript for this round only:

- `oap/active`
- `oap/orders/156-a-agentic-doctrine-and-codex-0149-client-contract.md`
- `oap/reports/156-a-agentic-doctrine-and-codex-0149-client-contract.md`

No other path is authorized. In particular,
`AGENTIC_CLIENT_INTEGRATION.md` is inherited read-only and must not change.
If an in-scope implementation genuinely requires another path, stop and
publish a truthful failed report rather than expanding scope yourself.

## Part A — adopt the inherited permanent doctrine

### Constitution hierarchy and precedence

In `AGENTS.md`:

1. Add `AGENTIC_CLIENT_INTEGRATION.md` explicitly to the durable
   authority/contract hierarchy at the existing Section 5.1 contract-document
   location.
2. State explicitly that it is the detailed normative contract for adding or
   changing agentic-client integrations.
3. State that the concise `AGENTS.md` section is the implementation
   constitution/reminder for that subject.
4. State that if the concise summary and detailed contract diverge, the
   detailed contract governs the agentic-client integration subject, subject
   to the repository's existing human/OAP authority hierarchy.
5. Do not copy the full doctrine into `AGENTS.md`.

### Required concise section

Insert the following Part-XVIII block verbatim except for purely mechanical
formatting required by its location in `AGENTS.md`:

### Agentic client integrations

`AGENTIC_CLIENT_INTEGRATION.md` is authoritative for adding or changing support
for Codex, OpenCode, Antigravity, Claude Code, Gemini CLI, Aider, or any other
agentic client.

A product/brand or “OpenAI-compatible” claim is never a compatibility key.
Support must be pinned to one exact executable/distribution version, source
contract where available, model/catalog/config profile, structural fixtures,
client-module version, and explicit client/server pairing.

Client modules are pure, static, non-authoritative dialect decoders. They must
not authenticate, route, grant tools, access PostgreSQL/Redis, perform HTTP, or
own quota/accounting. Server modules are exact downstream transports and must
not own public authentication or policy. The Gateway core retains all
authority.

Client-specific reasoning, metadata, tool, identifier, replay, and SSE behavior
must remain version-owned and default-false. Do not globally relax the ordinary
OpenAI contract. Do not fabricate item IDs, treat null as non-null state, infer
hosted authority from tool names, or accept ID-less replay without a
cryptographically authenticated same-key fallback and no-downgrade proof.

Every agentic profile requires exact-client structural capture, natural
two-turn fake conformance, producer-against-actual-consumer tests, executed
PostgreSQL replay/accounting tests, a machine-checked `missing=[]` obligation
manifest, and an explicitly authorized hook-free protected multi-turn run.
Reports are immutable claims, not proof; strategic review must inspect actual
test collection/execution and GitHub state.

Temporary production diagnostic hooks must be removed before acceptance.
After acceptance, freeze behavior and decompose/review the evidence branch
before adding another client.

Do not paraphrase that block into weaker or broader language.

### Durable links

Add a clear relative link to root `AGENTIC_CLIENT_INTEGRATION.md` from each of:

- `docs/module-architecture.md`
- `docs/responses-compatibility.md`
- `docs/compatibility-matrix.md`

The link text must identify the root document as the detailed normative
agentic-client integration contract. Do not duplicate its complete prose.

### Governance test

Add a focused repository test at
`tests/unit/test_agentic_client_integration_governance.py` proving at minimum:

- root `AGENTIC_CLIENT_INTEGRATION.md` exists;
- `AGENTS.md` explicitly names it as agentic-client integration authority;
- `### Agentic client integrations` exists;
- the bounded section retains the critical invariants that client modules are
  non-authoritative, client-specific behavior is version-owned and
  default-false, exact-client natural multi-turn qualification is required,
  and temporary production diagnostics are removed before acceptance;
- all three required documentation links exist and resolve to the root file.

The test must inspect bounded semantic markers within the section, not require
the complete prose block or full doctrine to remain byte-identical forever.
Future separately reviewed edits must remain possible.

## Part B — reconstruct the Codex 0.149 client contract

Reconstruct only the accepted structural/session client layer represented by
the selected paths at `4eb768...`. This layer may decode and classify untrusted
syntax but grants no runtime authority.

### Exact selected production/tooling state

Unless a mechanical adjustment is strictly required by the new governance
test/docs and is documented, the following selected paths must reproduce these
read-only source blobs from `4eb768...`:

| Path | Target Git blob |
|---|---|
| `app/slaif_gateway/modules/clients/codex_0149.py` | `c196eb2f9608248303d6d9f2126d1d7596438866` |
| `app/slaif_gateway/modules/contracts.py` | `653ec8f8770c2c5c464663d614bda126d6e5ace7` |
| `app/slaif_gateway/services/responses_request_policy.py` | `88f3ff334818aa31b06dbf12066beb224e6b5bc1` |
| `scripts/capture_codex_protocol.py` | `7bc06d39fedbe3d6d6957137c5afc0e751f38f77` |
| `tests/fixtures/codex/0.149.0/responses-structural-v2.json` | `c182dd195312368d58c80f25c915e83e8474a470` |
| `tests/fixtures/codex/0.149.0/responses-session-relationship-v3.json` | `a0073a638b82750b3752ac5b78f5df91f97d7d56` |

Do not copy selected paths from final `acea2af4...` where that would pull
visible-reasoning or ID-less-tool replay behavior assigned to Objectives 159
and 160.

### Required client behavior

- `codex-0.149-responses-v1` becomes the accepted structural/session module
  version 3, tied to the canonical v3 session relationship fixture and the v2
  structural fixture provenance.
- Exact task-local npm `@openai/codex@0.149.0` capture recognizes the bounded
  top-level declaration set observed in the accepted fixture, including
  function, custom, `tool_search`, and `web_search` structural classes.
- `tool_search` and `web_search` remain adapter-managed candidate facts only.
  They do not become hosted-tool requests, external-tool accounting, route or
  provider authority, or Gateway execution authority.
- Candidate field sets, values, type classes, nesting, cardinality, and size
  remain bounded. URLs, credentials, headers, MCP/connectors, preview aliases,
  nested search declarations, unknown authority fields, malformed shapes, and
  unsupported explicit search choices fail closed without echoing values.
- The module requires equal canonical UUID `session_id` and `thread_id`
  aliases for its accepted session namespace and returns exactly one transient
  internal `session_id` hint.
- Installation, root-turn, turn, cache, item, unknown, extra, malformed,
  ambiguous, noncanonical, control-bearing, URL-like, or over-bound identity
  material does not become a session hint and is not retained, logged,
  audited, exported, persisted, hashed as identity truth, or forwarded.
- Request policy removes client metadata before provider-body construction and
  preserves candidate declarations only when supplied by the exact module with
  exact declared shapes and independent existing capability gates.
- Default OpenAI and Codex 0.147 behavior remain unchanged.

### Mandatory intermediate merge-safety boundary

Objective 156 must not add `local-coding-v1`, modify the server registry, or
register the eventual Codex-0.149/Local-Coding compatibility pair. The client
module and fixtures may name the exact reviewed target pair as non-authorizing
protocol metadata, but actual runtime selection must still fail through the
existing no-compatible-server-pair gate before reservation, ledger, provider,
or network work.

Add a direct regression proving the selected 0.149 module has no active server
pair at this layer and cannot be used to reach an existing generic/OpenAI,
OpenRouter, facial-scoring, hosted-tool, or other server path. Objective 157
alone owns the later literal `local-coding-v1` server and pair registration.

## Negative, security, privacy, and accounting evidence

Prove at minimum:

- client-module selection still comes only from complete server-side module
  metadata with exact module version and fixture digest;
- product name, User-Agent, model name, request shape, or client metadata does
  not select the module;
- the module never authenticates, routes, accesses PostgreSQL/Redis, performs
  HTTP, reserves quota, prices, persists state, or grants a tool;
- missing/malformed/unequal session aliases and historical old metadata reject
  before reservation and ledger side effects in PostgreSQL;
- no raw prompts, descriptions, schemas, tool values, metadata values, IDs,
  credentials, headers, temporary paths, or client output enter fixtures,
  logs, test output, errors, documentation examples, or OAP artifacts;
- candidate declarations do not enter hosted-search admission, external-tool
  fence/hold state, hosted-tool fees, or provider authority;
- unknown or newly observed structures fail closed;
- no production/provider/Local-Coding/Qwen call is made.

## Required verification

Use focused evidence; do not run an unrelated complete local suite.

1. Run the new doctrine/governance test.
2. Run the complete affected unit files:
   - `tests/unit/test_agentic_client_integration_governance.py`
   - `tests/unit/test_codex_client_modules.py`
   - `tests/unit/test_codex_protocol_capture.py`
   - `tests/unit/test_responses_request_policy.py`
3. Provision/use the repository-standard disposable PostgreSQL test
   environment and execute
   `tests/integration/test_codex_client_modules_postgres.py`; required cases
   may not be skipped, xfailed, or merely collected.
4. Validate both checked-in 0.149 fixtures using the permanent capture tool.
5. Install/resolve an exact task-local `@openai/codex@0.149.0` without changing
   the host Codex installation. Run one fresh loopback-only structural fixture
   comparison and one A/resume-A/B session relationship comparison through
   the permanent capture tool. No provider credential, Local Coding, Qwen, or
   real model call is authorized.
6. Run Ruff formatting/checks and Python compilation for all changed Python
   paths.
7. Mechanically inspect the final diff and blob targets. The only `app/`
   changes from base must be the three allowed production files, and they must
   have the target blob identities above.
8. Prove `AGENTIC_CLIENT_INTEGRATION.md` is unchanged from base, including blob
   `7c48c679...` and SHA-256 `1b498f8d...`.
9. Prove no Local server module/pair, streaming lifecycle, visible-reasoning
   compatibility, ID-less replay, replay repository/service, signed identity,
   provider adapter, accounting logic, or Objective-155 diagnostic machinery
   entered the diff.
10. Push the implementation, open the unique PR, and require every normal
    GitHub check on the exact implementation/report head to complete
    successfully. A pending, skipped, cancelled, missing, or failed check is
    not green.

If an unchanged broad CI job exposes a failure outside allowed scope, report
it truthfully and stop; do not modify unrelated paths without a strategic
continuation.

## Documentation requirements

- `AGENTS.md` adopts the existing doctrine as specified above.
- The three required durable links are present.
- Update only the bounded Codex-0.149 client-contract portions of the allowed
  docs. They must distinguish structural/default-denied reconstruction from
  active Local-Coding pairing, live qualification, deployment qualification,
  release, or production readiness.
- Do not copy Objective-155 verifier prose, protected-runtime details, PR-head
  conditions, or temporary diagnostics into permanent docs.
- The report must include the exact documentation-impact statement required by
  `AGENTS.md`.

## Explicit non-goals

Do not:

- change `AGENTIC_CLIENT_INTEGRATION.md`;
- activate or implement Objective 157, 158, 159, or 160;
- add `local-coding-v1` or any client/server pair;
- add Local transport, signed identity, provider factory, route, Gateway
  orchestration, or Local-Coding configuration behavior;
- add reasoning/function/message SSE lifecycle behavior;
- add visible-reasoning, null-encrypted, ID-less tool-call, call-ID-HMAC, or
  other replay behavior;
- add a generic agentic-client, OpenCode, Antigravity, Claude Code, Gemini CLI,
  Aider, dynamic plugin, SDK, or discovery framework;
- globally relax OpenAI Responses validation;
- grant hosted-tool/provider/MCP/network authority;
- modify accounting, quota, pricing, routing, audit, schema, migrations, or
  production configuration;
- copy `scripts/verify_local_coding_full_stack.py` or its Objective-specific
  test file;
- make protected or real-provider requests;
- modify, close, merge, rewrite, or force-push PR #291;
- merge or auto-merge the new PR;
- claim final clean-stack, Local-Coding, deployment, release, certification, or
  production acceptance.

## Setup and external-boundary authority

Routine task-local installation of exact Codex 0.149 and provisioning of a
disposable loopback PostgreSQL test database are authorized. Preserve the host
Codex installation and all unrelated containers/databases/worktrees. No
production database, credential, endpoint, Local Coding process, protected
Qwen, external provider, or non-loopback service may be used. Clean up only
resources created uniquely for this objective and report the cleanup state.

## Publication and immutable report duties

Create exactly one immutable report:

`oap/reports/156-a-agentic-doctrine-and-codex-0149-client-contract.md`

The report must contain:

- `RESULT=PASSED` or `RESULT=FAILED`;
- repository, base, branch, PR number/URL/state, and no-auto-merge state;
- literal implementation head SHA;
- `Report publication commit: SELF`;
- confirmation that the report-only commit's first parent is the implementation
  head and only the report path changed;
- exact changed-path inventory and `app/` diff inventory;
- the selected blob identity table and actual final blob IDs;
- inherited doctrine blob/SHA, explicit unchanged result, `AGENTS.md` adoption,
  precedence statement, and all three documentation-link results;
- the governance test result without claiming full-prose immutability;
- module version/profile/fixture digests and exact client-source provenance;
- bounded results of fresh structural and session captures, including explicit
  zero-provider-call status;
- explicit proof that no active 0.149 server pair exists in this intermediate
  PR and rejected runtime selection causes zero accounting/provider side
  effects;
- exact focused unit/PostgreSQL/Ruff/compile results, including counts and any
  skip/xfail/failure state;
- GitHub check names and final states on the exact head;
- privacy/security/accounting evidence and cleanup result;
- documentation impact statement;
- explicit limitations: this is doctrine adoption plus a default-denied client
  contract only, not Local-Coding activation or final clean-stack acceptance.

Publish the implementation commits, then the final report-only commit. Verify
the remote PR head is the report commit, its first parent is the reported
implementation head, and every claimed GitHub artifact exists. Only then write
exactly the two bytes `OK` with no newline to the response FIFO and return to
the control-FIFO wait.
