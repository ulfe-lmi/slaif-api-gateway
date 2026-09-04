# OAP Work Order — 157-a

## Objective and business reason

Create the second clean post-Objective-155 decomposition PR from merged
Objective-156 main. Reconstruct the accepted `local-coding-v1` server module,
its exact Codex-0.149 pairing, Responses-only transport, and final signed
identity/secret/route containment.

This objective must be independently merge-safe. It enables only the bounded
Local transport and mocked-conformant identity/accounting foundation. Advanced
Codex reasoning/function/message stream lifecycles, visible-reasoning replay,
ID-less tool-call replay, and final two-turn acceptance remain absent and
fail-closed until Objectives 158–160.

## Verified starting state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Remote `main` is exactly merged Objective-156 commit
  `f45bbd6f0eb9dbccbe39f9c9bd785c12218d2459`.
- Objective 156 PR #293 is merged. Its frozen implementation head is
  `5e37809e339a29178036a8793b223be8c3776a4a`; immutable PASSED report head is
  `db283c45434693646ccbbaa2aeb82104641e30c3`.
- Main contains the permanent root `AGENTIC_CLIENT_INTEGRATION.md`, its
  `AGENTS.md` adoption, all required links, and the default-denied Codex 0.149
  version-3 structural/session client contract.
- Codex 0.149 currently has no active server pair; runtime selection fails
  before accounting/provider side effects.
- Objective 155 remains permanently closed. PR #291 is the untouched
  acceptance/evidence branch at report head
  `45eeeb538e95ab3ae1d4d6e78ffb654e0e496fa2`; accepted implementation head is
  `acea2af4ca0f4586fc159c91607e1848f53f1107`.
- Accepted final `app/` tree target remains
  `bd536a282362cc549cc0c5518db8e743af667b63`.
- Use Objective-155 commit
  `4eb768254fcde0a4108bcabb35f175a74bd07a3f` only as the read-only
  pre-stream/pre-replay Local transport/orchestration source. Overlay the final
  accepted Local identity and signed-route grammar blobs from `acea2af4...` as
  explicitly listed below. Do not cherry-pick either commit wholesale.
- Exact unchanged Local Coding consumer authority for conformance is
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa` from `ulfe-lmi/slaif-local-coding`
  PR #7. It is read-only; do not modify its repository, PR, branch, config, or
  runtime.
- No Objective-157 branch or PR exists at activation.
- Preserve all unrelated worktrees, branches, local artifacts, containers,
  databases, and `.local-provider-catalog/` state.

## PR contract

- PR mode: `CREATE_NEW_PR`
- Base branch: `main`
- Exact base SHA: `f45bbd6f0eb9dbccbe39f9c9bd785c12218d2459`
- Branch: `oap/157-local-coding-server-signed-identity`
- PR title: `obj157: reconstruct Local Coding server and signed identity`
- Create exactly one PR for Objective 157.
- Do not merge or enable auto-merge.
- Do not modify, close, rewrite, squash, rebase, or force-push PR #291.
- If remote main moves, keep the exact authorized base and report it; do not
  silently absorb unrelated changes.

Use a clean isolated linked worktree. Do not switch/reset/clean/stash an
existing worktree. Commit this exact order and `oap/active` unchanged on the
new branch.

## Required reading

Before editing, read completely:

- `AGENTS.md` and root `AGENTIC_CLIENT_INTEGRATION.md`;
- `OAP-COMMUNICATION-coding-agent.md`;
- the merged Objective-156 implementation/report and current module contracts;
- current `docs/module-architecture.md`, `docs/provider-forwarding-contract.md`,
  `docs/responses-compatibility.md`, `docs/compatibility-matrix.md`,
  `docs/configuration.md`, `docs/security-model.md`, and `docs/accounting.md`;
- the exact selected paths at read-only source commit `4eb768...`;
- the final accepted `contract.py`, `identity.py`, and their security tests at
  `acea2af4...`;
- the Local Coding signed-identity/tool-filter contract and actual verifier at
  exact read-only Local head `4d3ab2f...`.

## Allowed paths

Production:

- `app/slaif_gateway/config.py`
- `app/slaif_gateway/modules/clients/openai_default.py`
- `app/slaif_gateway/modules/servers/local_coding/__init__.py`
- `app/slaif_gateway/modules/servers/local_coding/adapter.py`
- `app/slaif_gateway/modules/servers/local_coding/contract.py`
- `app/slaif_gateway/modules/servers/local_coding/identity.py`
- `app/slaif_gateway/modules/servers/registry.py`
- `app/slaif_gateway/providers/factory.py`
- `app/slaif_gateway/schemas/providers.py`
- `app/slaif_gateway/services/responses_gateway.py`

Permanent fixtures/tests:

- `tests/fixtures/local_coding/responses_tool_filter_vectors.json`
- `tests/fixtures/local_coding/signed_identity_v1_vectors.json`
- `tests/integration/test_local_coding_server_module_postgres.py`
- `tests/unit/test_local_coding_server_module.py`
- `tests/unit/test_module_architecture.py`
- `tests/unit/test_provider_factory.py`
- `tests/e2e/test_openai_python_client_responses.py`

Permanent documentation:

- `docs/accounting.md`
- `docs/compatibility-matrix.md`
- `docs/configuration.md`
- `docs/module-architecture.md`
- `docs/provider-forwarding-contract.md`
- `docs/responses-compatibility.md`
- `docs/runbooks/provider-key-rotation.md`
- `docs/security-model.md`

OAP transcript:

- `oap/active`
- `oap/orders/157-a-local-coding-server-and-signed-identity.md`
- `oap/reports/157-a-local-coding-server-and-signed-identity.md`

No other path is authorized. Root `AGENTIC_CLIENT_INTEGRATION.md`, the
Objective-156 client paths, and every Objective-155 order/report are read-only.

## Exact reconstruction targets

Reconstruct the following production blobs exactly:

| Path | Required target blob | Source |
|---|---|---|
| `app/slaif_gateway/config.py` | `24f686830357c270a1205236d69833edd70880d5` | accepted/final |
| `app/slaif_gateway/modules/clients/openai_default.py` | `72644850a93eb740324f436702c22afd1c79e369` | accepted/final |
| `app/slaif_gateway/modules/servers/local_coding/__init__.py` | `191c07089aba4af81a30a00461272a6868ba473f` | accepted/final |
| `app/slaif_gateway/modules/servers/local_coding/adapter.py` | `2ffe984bc593656342b45a246ec716387d1849bf` | accepted/final |
| `app/slaif_gateway/modules/servers/local_coding/contract.py` | `af12e3b26641051c0085f72a1f974a788b6ccf6b` | final grammar-corrected |
| `app/slaif_gateway/modules/servers/local_coding/identity.py` | `c2b87416352ee584eec0a29704e68e6ca29395fb` | final grammar-corrected |
| `app/slaif_gateway/modules/servers/registry.py` | `f29b835f7b7e627b5a2a6a06b27c1b222c6be5cc` | accepted/final |
| `app/slaif_gateway/providers/factory.py` | `cb0f5048547393ee7595f31b3b71da1dfb7bcc6b` | accepted/final |
| `app/slaif_gateway/schemas/providers.py` | `81d48f69213324e8ddce4a6c0ae9f30afd758b08` | accepted/final |
| `app/slaif_gateway/services/responses_gateway.py` | `cd9424edf08450e5fb818193133fe5643c4cd33a` | pre-stream/pre-replay source |

The mixed target is deliberate: final identity/route grammar corrections must
be present from first clean introduction, while later stream/replay changes in
final `responses_gateway.py` remain assigned to Objectives 158–160.

Required permanent fixture blobs:

- `responses_tool_filter_vectors.json`:
  `cdd33cb5c52377f80282803f53005074df091fc8`
- `signed_identity_v1_vectors.json`:
  `e1e4c43e10318ff3170859876dc4d8f6f7d5bdb9`

Do not replay historical insecure intermediate identity encodings. Do not
reformat exact accepted-source blobs merely to satisfy a non-repository
formatter; repository Ruff `check` remains mandatory.

## Required product behavior

### Static server and pair containment

- Add literal server module `local-coding-v1` only for an exact complete
  top-level Local Coding route contract and provider kind
  `openai_compatible`.
- Add exactly one Codex-0.149 pair:
  `codex-0.149-responses-v1 -> local-coding-v1`.
- The pair is non-authorizing: endpoint, key, route, model, capability,
  pricing, quota, accounting, identity, and tool gates remain independent.
- Arbitrary/default/OpenAI/Codex-0.147 clients, generic compatible providers,
  hosted routes, facial scoring, and unknown server modules do not inherit the
  pair.
- The adapter supports only Responses create and Responses SSE transport.
  Chat, compact, input-token, stored-resource, Conversations, Audio,
  Embeddings, Realtime, and every other operation reject before HTTP.

### Transport and credential boundary

- Serialize the final canonical Responses mapping exactly once as
  deterministic UTF-8 JSON and send those exact bytes with `content=...`.
- Substitute a separate Local service Bearer from the provider row; never
  forward the public Gateway bearer, cookies, caller headers, or arbitrary
  `X-SLAIF-*` input.
- Preserve the approved Local tool-declaration candidates only through the
  exact pair; never convert them into hosted search, Gateway execution,
  provider authority, external-tool pricing/fence/hold state, or arbitrary
  server selection.
- Enforce body, timeout, redirect/retry, response content type, JSON/SSE, and
  failure mapping bounds exactly as the accepted adapter does.

### Identity authority and signed wire

- Authenticated Gateway owner UUID and Gateway-key UUID remain the security
  principal/accounting authority.
- The corroborated Codex `session_id` is an untrusted namespace below that
  authority; repository scope and route are server-side facts.
- Derive principal/session/repository with separate domain-separated HMACs and
  a dedicated derivation secret. The session binding includes the authenticated
  Gateway key so same-owner/same-client-session traffic through another key is
  isolated.
- Every derived principal/session/repository value must be an unconditional
  `h` prefix plus the complete unpadded base64url HMAC-SHA256 digest. Preserve
  all 256 digest bits; never conditionally prefix, truncate, retry, randomize,
  or expose source inputs.
- Validate principal, session, repository, and signed route against exact
  Local-v1 grammar `^[A-Za-z0-9][A-Za-z0-9_-]{0,255}$` before signing or
  forwarding. Static route parsing may retain its separately accepted grammar;
  never silently rewrite a signed route.
- Bind the signature to version, method, path, raw-query digest, exact-body
  digest, principal, session, repository, route, timestamp, and nonce.
- Use fixed signed-header cardinality and a fresh bounded nonce/timestamp;
  never log or persist raw identity, signature, nonce, canonical bytes, body
  digest, source UUIDs, session hints, or secrets.

### Secret separation and replay/deployment limits

- Local service Bearer, identity-derivation secret, and signing secret are
  distinct bounded roles and must be constant-time checked against each other
  and known core/provider/admin/one-time-secret roles.
- Signed mode requires the accepted `single_worker` and
  `process_local_ttl_lru` Local contract. Do not claim multi-worker,
  restart-persistent replay protection, overlapping key rotation, hostile
  same-bearer tenancy, or production qualification.
- Invalid/missing secrets, context, route, metadata, body size, header state,
  signature inputs, or configuration fail before network/provider work.

### Accounting boundary

- One admitted public Local request uses one ordinary `strict_bounded`
  PostgreSQL reservation and one terminal ledger outcome.
- Provider usage returned through Local is authoritative for finalization.
- Local internal compiler/governance calls do not create Gateway accounting
  rows.
- Identity/auth/route/policy/transport failures use existing provider failure
  law and leave no pending reservation.
- Adapter-managed search candidates create no hosted-tool fee, external-tool
  capability/destination, fence, hold, provider, or route metadata.

## Intermediate merge-safety

This PR must not modify `app/slaif_gateway/providers/streaming.py`, replay
repository/service code, or the Objective-156 Codex client/policy blobs.

The pair may carry ordinary/mock-conformant Responses create and already-safe
streaming shapes, but unimplemented reasoning/function/message lifecycle
variants must continue to fail through the existing strict validator. No
fixture, capability, test, or documentation may claim Objective-158 streaming
support, Objective-159 visible reasoning, Objective-160 ID-less replay, or the
final real two-turn qualification.

## Required permanent tests

Add/reconstruct focused tests proving at minimum:

- exact route contract fields, defaults, bounds, unknown-field denial,
  provider-kind containment, deployment/replay mode, and signed-route grammar;
- exact one-pair registry and cross-client/server denial matrix;
- every non-Responses adapter method rejects before HTTP;
- service Bearer substitution and public-bearer/internal-header absence;
- exact UTF-8 body bytes are the bytes signed and sent;
- deterministic identity stability and owner/key/session/repository/route
  isolation;
- fixed legacy `-` and `_` pre-prefix vectors now produce collision-free,
  alphanumeric-leading full-digest identities;
- signed fields and dotted/leading-punctuation signed routes fail before
  network work while valid internal `-`/`_` characters pass;
- service/signing/derivation/core/provider secret equality and malformed
  secrets fail without exposing values;
- missing/malformed/ambiguous session context and invalid route context fail
  before adapter/provider/accounting work;
- fixture canonical bytes/signature and body/signature tampering rejection;
- mocked official OpenAI-client non-streaming and safe streaming Local flows;
- same session reuse, different session isolation, and same session through a
  different Gateway key isolation;
- ordinary reservations/ledger finalization, provider usage, zero pending,
  and complete absence of external-tool accounting facts;
- PostgreSQL identity/pre-admission failures produce no reservation/ledger
  side effects;
- module architecture and provider factory do not bypass the core.

## Actual Local consumer conformance

Without modifying or starting protected Local/Qwen product services, run a
finite deterministic synthetic cross-contract matrix against the actual
unchanged Local verifier at exact head `4d3ab2f...`.

Use at least 16 combinations spanning multiple owner UUIDs, Gateway-key UUIDs,
canonical session UUIDs, repository scopes, and both legacy leading `-` and
`_` vectors. Prove only bounded counts/booleans:

- all four signed fields satisfy consumer grammar;
- exact-body signing is accepted;
- body tamper and signature tamper reject with fresh replay state;
- nonce replay rejects;
- raw owner/key/session/repository inputs are absent from derived identity and
  retained evidence.

Do not retain values, credentials, signatures, headers, bodies, nonces,
timestamps, digests, canonical bytes, prompts, tool contents, or errors. If
the final accepted producer fails the pinned consumer, publish FAILED and stop;
do not modify Local Coding.

## Required verification

Use focused tests, not an unrelated complete local suite:

1. Complete affected unit files:
   - `tests/unit/test_local_coding_server_module.py`
   - `tests/unit/test_module_architecture.py`
   - `tests/unit/test_provider_factory.py`
2. Execute `tests/integration/test_local_coding_server_module_postgres.py`
   against a repository-standard disposable PostgreSQL database with no
   required skip/xfail/failure.
3. Execute the affected Local-Coding tests in
   `tests/e2e/test_openai_python_client_responses.py` with disposable
   PostgreSQL and mocked loopback Local transport. No external provider call.
4. Execute the actual-Local consumer conformance matrix described above.
5. Run repository Ruff `check` and Python compilation on changed Python paths.
6. Run `git diff --check`, fixture canonicalization/privacy checks, secret
   canaries, and exact blob verification.
7. Mechanically prove the only production paths changed from base are the ten
   allowed app paths and they equal the required blobs.
8. Prove no diff to `AGENTIC_CLIENT_INTEGRATION.md`, Objective-156 client
   blobs, production streaming validator, replay repository/service, schema/
   migrations, or Objective-155 verifier machinery.
9. Push the implementation, create the unique PR, and require all ten normal
   GitHub checks on the exact final report head to succeed.

Skipped, missing, pending, cancelled, xfailed, or environment-blocked required
evidence is not a pass. If an unchanged broad CI job fails outside allowed
scope, report truthfully and stop rather than editing unrelated paths.

## Documentation requirements

Update allowed permanent docs to describe only implemented 157 behavior:

- exact static pair and non-authorizing status;
- Responses-only Local transport and separate service Bearer;
- HMAC pseudonymization, producer-side consumer grammar, exact-body signing,
  secret roles, and session namespace authority;
- process-local/single-worker replay and rotation limitations;
- ordinary strict-bounded accounting and absence of hosted-tool facts;
- mocked/cross-contract conformance only, not advanced stream/replay or live
  model qualification.

Preserve the permanent root doctrine links. Do not copy Objective-155
verifier, protected-runtime, report-head, PR-#291, or temporary diagnostic
prose. Include the required documentation-impact statement in the report.

## Explicit non-goals

Do not:

- modify Local Coding or Qwen;
- use protected credentials or make real provider/model calls;
- implement Objective 158, 159, or 160;
- add exact advanced Codex reasoning/function/message SSE lifecycle support;
- add visible-reasoning/null-encrypted/ID-less tool-call/call-ID-HMAC replay;
- modify production replay services/repositories or database schema;
- broaden ordinary OpenAI/default/Codex-0.147 behavior;
- grant hosted-search, MCP, connector, Gateway tool execution, or provider
  authority;
- add dynamic plugins, generic agent clients, or the later Responses/transport
  refactor;
- copy the Objective-155 full-stack verifier or its tests;
- modify inherited doctrine or PR #291;
- merge or auto-merge;
- claim final clean-stack, protected, deployment, release, certification, or
  production acceptance.

## Setup authority and cleanup

Routine task-local dependencies, a disposable PostgreSQL database, loopback
HTTP mocks, and a read-only task-local checkout/worktree of exact Local head
`4d3ab2f...` are authorized. Do not alter the existing Local worktree or its
PR. Do not use production data, protected Qwen, or provider credentials. Clean
up only uniquely created resources and report their absence.

## Immutable report duties

Publish exactly one report:

`oap/reports/157-a-local-coding-server-and-signed-identity.md`

It must contain:

- `RESULT=PASSED` or `RESULT=FAILED`;
- exact repository/base/branch/PR state and no-auto-merge state;
- implementation head and `Report publication commit: SELF`;
- report-only topology and complete changed-path/app inventory;
- every required production/fixture target blob and actual blob;
- exact pair matrix and explicit later-feature absence;
- identity authority, grammar, HMAC representation, signature, secret-role,
  transport/header, and route containment evidence;
- actual-Local head and bounded matrix row/pass/tamper/replay/privacy counts;
- focused unit/integration/E2E/Ruff/compile/diff/privacy results with skips and
  failures explicit;
- PostgreSQL reservation/ledger/zero-pending/external-fact results;
- all ten exact report-head GitHub check states;
- cleanup, documentation impact, and honest limitations;
- confirmation PR #291, Local, Qwen, Objective 158+, and protected systems were
  untouched.

Commit implementation, then a final report-only commit whose first parent is
the implementation head and only changed path is this report. Verify the
report commit is the remote PR head and every claimed GitHub state exists.
Only then write exactly `OK` to the response FIFO and return to one blocking
control-FIFO read.
