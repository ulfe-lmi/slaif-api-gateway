# OAP Work Order — 155-b

PR mode: `AMEND_EXISTING_PR`
PR: `#291`
Branch: `oap/155-local-coding-signed-server-module`
Base: `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`
Current remote head: `abe872c5e8262af042c7803be4682db9c138c8bc`

## Objective and reason

Close three containment defects found in independent review of 155-a:

1. `LocalCodingAdapter` subclasses `OpenAIProviderAdapter`. It overrides
   Responses create/stream, but inherits Chat, input-token, compact,
   stored-response, Conversation, Audio, Embeddings, and Realtime methods that
   serialize through ordinary `json=...`/multipart paths and emit no signed
   identity. A Local Coding route contract on another endpoint could therefore
   reach an unsigned inherited method.
2. Settings separate signing and derivation from known Gateway/provider secrets,
   but the Local Coding service Bearer comes from an arbitrary provider
   `api_key_env_var`; adapter construction does not reject equality between
   that service credential and either signing/derivation secret.
3. Tests prove pure derivation and direct adapter signing, but do not prove the
   core `_build_local_coding_server_context` boundary derives opaque context
   from authenticated owner truth, transient session hints, server-side
   repository scope, and resolved route facts or fails safely when any input is
   missing/ambiguous.

Repair these gaps without adding Codex 0.149 pairing, Local Coding features, or
live work. Previous reports are immutable.

## Verified starting state

- PR #291 is open, non-draft, mergeable, clean, no auto-merge; all ten report-
  head checks passed.
- Report head `abe872c5e8262af042c7803be4682db9c138c8bc` has implementation head
  `c48c61a673b250d193e25a36b495e6d7acae10f7` as first parent and changes only
  the 155-a report.
- Pinned Local Coding PR #7 remains open/green at exact head
  `356be8345dd71d6fddf829278651d18e485731d4`; Gateway merge remains forbidden.
- The current static default-client mocked conformance, fixtures, PostgreSQL
  tests and cross-repo fake-Qwen result are retained.

## Required implementation

### 1. Responses-create-only adapter

- Prefer making `LocalCodingAdapter` inherit directly from `ProviderAdapter`
  and own only the minimum safe Responses create/stream parsing helpers, or
  otherwise explicitly override every non-Responses-create method inherited
  from OpenAI to fail with `UnsupportedProviderEndpointError` before HTTP.
- The class must support only:
  - `forward_response` for exact `/v1/responses`/`responses`; and
  - `stream_response` for the same exact operation.
- Chat Completions, Responses input-token count, compact, retrieve/delete/input
  items, Conversations and items, Audio, Embeddings, Realtime, and every other
  ProviderAdapter method must fail before HTTP and before an unsigned service
  call.
- Add a parametrized test over every current public ProviderAdapter operation,
  proving only the two Responses-create operations can reach transport.
- Add an architecture guard preventing future inheritance from
  `OpenAIProviderAdapter` or direct use of its ordinary `_post_json`/
  `_stream_sse` helpers in the Local Coding server package.

### 2. Mechanical service/signing/derivation separation

- During exact Local Coding adapter construction for signed mode, validate the
  configured service Bearer with the same visible-ASCII bounds and compare it
  constant-time against active signing and derivation secret bytes.
- Equality with either secret fails with one bounded
  `local_coding_secret_roles_not_separate` configuration error before HTTP.
- Preserve static mode behavior without requiring unused signing/derivation
  secrets, but if those values are configured they must still not equal the
  service credential.
- Tests must cover service=signing, service=derivation, signing=derivation,
  equality with known core secrets, malformed service bytes, and all-distinct
  success without printing values.

### 3. Core identity-context boundary proof

- Add focused tests for `_build_local_coding_server_context` or a promoted pure
  core helper using:
  - authenticated owner UUID;
  - selected client request transient session hints;
  - server-side `local_coding_repository_scope` key/profile policy;
  - exact resolved Local Coding route contract; and
  - dedicated derivation secret.
- Prove output contains only opaque principal/session/repository/route/mode,
  no raw owner/session/repository values, and is stable for the same inputs but
  isolated across owner, session, repository, and route changes.
- Prove missing/ambiguous session, missing repository binding, missing secret,
  non-Local-Coding route, malformed route contract, and static mode behavior.
- The test may invoke the core helper directly because Codex 0.149 pairing is
  intentionally deferred; it must not create an unauthorized pair merely to
  obtain a full handler success.
- Documentation/report must say signed core derivation is boundary-tested and
  adapter/pinned-app conformant, not yet Codex-composed E2E.

## Exact allowed paths

```text
app/slaif_gateway/config.py
app/slaif_gateway/modules/servers/local_coding/**
app/slaif_gateway/modules/servers/registry.py
app/slaif_gateway/providers/factory.py
app/slaif_gateway/services/responses_gateway.py
tests/unit/test_local_coding_server_module.py
tests/unit/test_module_architecture.py
tests/unit/test_provider_factory.py
tests/integration/test_local_coding_server_module_postgres.py
tests/e2e/test_openai_python_client_responses.py
docs/module-architecture.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/security-model.md
docs/configuration.md
docs/compatibility-matrix.md
oap/orders/155-b-endpoint-secret-and-core-identity-containment.md
oap/reports/155-b-endpoint-secret-and-core-identity-containment.md
oap/active
```

Use the narrowest subset. No route/client pair, schema, migration, Compose, or
external-repository change is authorized.

## Required verification

- Focused Local Coding unit/architecture/factory/config/header tests including
  every ProviderAdapter operation and secret-equality matrix.
- Core identity helper positive/isolation/negative tests.
- Retain focused PostgreSQL and default-client mocked E2E; rerun if behavior
  paths change.
- Re-run pinned Local Coding fake-Qwen conformance only if transport/signature
  code changes; otherwise verify fixture and prior implementation evidence.
- Ruff changed Python, `git diff --check`, docs checker/tests, final GitHub CI/
  CodeQL.
- No broad suite, real provider/Qwen, Codex pair, OpenCode, production Compose,
  email, deployment, or live credential.

## Anti-false-positive acceptance

- Checking only `request.endpoint` inside overridden Responses methods while
  leaving other inherited methods callable fails.
- Documentation saying “Responses only” without exhaustive operation tests
  fails.
- Comparing only statically named OpenAI/OpenRouter secrets while ignoring the
  dynamic service Bearer fails.
- Direct adapter identity tests without core derivation proof fail.
- Adding Codex 0.149 pairing to obtain a positive handler test fails.
- Any new protocol capability or weakened route/secret validation fails.

## Merge/dependency and publication

- Amend only PR #291; coding agent never merges or enables auto-merge.
- Local Coding PR #7 remains an external read-only pinned dependency and must
  not be modified.
- Publish exactly one immutable
  `oap/reports/155-b-endpoint-secret-and-core-identity-containment.md` as a
  report-only commit with the implementation head as first parent. Record
  endpoint matrix, secret matrix, core identity proof, focused/DB/E2E/cross-
  repo evidence, final checks and limitations; then send exact `OK`.
- Strategic merge remains forbidden while pinned Local Coding PR #7 is open.
