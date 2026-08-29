# OAP Work Order — 155-e

PR mode: `AMEND_EXISTING_PR`
PR: `#291`
Branch: `oap/155-local-coding-signed-server-module`
Base: `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`
Current remote head: `3e8c3505022908a5a107563b3ba0cb9633cf241c`

## Objective and reason

Correct the Local Coding identity model using current exact Codex 0.149
runtime evidence, then publish the minimum Gateway head required for the
already-prepared Local Coding `005-i` full-stack acceptance run.

The earlier Gateway identity code treated `session_id`, `thread_id`,
`turn_id`, and `root_turn_id` as interchangeable session hints. Local Coding
005-h proved the current 0.149 module exposes none of them because its
extractor keeps only `x-codex-*`. Human-directed architectural review then
stopped 155-d before code and required the concepts to be separated.

Fresh exact no-provider captures now establish the actual contract:

- with one private installation and explicit `codex exec resume <thread UUID>`,
  CLI thread ID, request `session_id`, and request `thread_id` are equal
  canonical UUID aliases and remain equal across the resumed request;
- a new Codex session/process under that same installation has a different
  CLI thread/session UUID;
- `root_turn_id`, `turn_id`, `prompt_cache_key`, and input-item IDs change
  across the resumed request and are not session identifiers;
- `x-codex-installation-id` remains equal across separate sessions and is too
  broad to identify one coding session.

Implement this exact relationship without making client metadata an
authentication authority. The Gateway-authenticated owner remains the
principal; the authenticated Gateway key additionally binds the session/cache
namespace; the corroborated Codex thread UUID is only an untrusted namespace
below those Gateway-owned facts. Replay, request identity/idempotency, quota,
and accounting remain separate.

## Verified starting state

- Canonical Gateway `main` remains
  `7ffce834915b74809109e8b579d8541cdcfa9df7`.
- Gateway PR #291 is OPEN, non-draft, MERGEABLE with no auto-merge at immutable
  155-d partial report head
  `3e8c3505022908a5a107563b3ba0cb9633cf241c`; its first parent is
  activation-only head `a88a52ef8d0d986e0f1ecdec95dc4025239f2859`, and the
  report commit changes only
  `oap/reports/155-d-stable-codex-session-identity-closure.md`.
- All ten 155-d report-head checks are successful. Round 155-d was deliberately
  stopped/superseded before product code; it only versioned its exact order,
  selector, partial report, and cleanup facts.
- Accepted 155-a/b/c implementation remains at 155-c implementation head
  `02670e3275ff57850aeaa9bc8aae4ed3c8e2f124`: exact Local Coding
  Responses-only transport/signing/secret containment, exact 0.149 candidate
  policy and pair, module-owned v2 policy, strict-bounded PostgreSQL evidence,
  and all ten checks passed.
- Local Coding PR #7 is OPEN, non-draft, MERGEABLE/CLEAN at immutable 005-h
  report head `6ee2a51aa7b03d4df46e0662d88cc33fd0ef7db8`; first parent
  is activation head `d2093650ef61200d3ed6ff9516bfd73eb2675182`; `test` is
  successful. Original signed-contract head
  `356be8345dd71d6fddf829278651d18e485731d4` remains an ancestor.
- Local 005-h passed exact Gateway capture/candidate/pair/provenance/tool-filter
  preflight and stopped before Docker/PostgreSQL/listeners/Qwen inference only
  because signed session context was unavailable. It found no Local Coding
  product defect.
- Current `derive_request_identity` derives opaque principal from authenticated
  owner UUID, opaque repository from server-side key policy, and opaque session
  from any one of four client hints. Current Codex 0.149 extraction returns all
  string-valued `x-codex-*` hints, including installation/turn metadata, and
  does not return a standard session alias.
- Local Coding rehydration/cache keys already contain opaque principal,
  session, repository, route, model/source, compiler/policy/version, and bounds.
  Its signed replay protection is nonce/timestamp/HMAC based and separate from
  session. Rehydration and replay state remain process-local with documented
  restart/multi-worker limitations.

## Normative identity model for this continuation

### Gateway-authenticated principal

- The authenticated Gateway owner UUID is the current human/account principal
  for this one-organization MVP. It is server-loaded from the validated bearer,
  never taken from client metadata.
- `gateway_key_id` remains authoritative for quota/accounting and additionally
  binds the Local Coding session namespace so two different Gateway
  credentials cannot share cache state accidentally, even for the same owner,
  repository, route, and client thread.
- Do not forward owner UUID, key UUID, public key ID, token hash, bearer, email,
  or organization labels. Only opaque HMAC-derived values cross to Local Coding.

### Client coding-session namespace

- Exact 0.149 `client_metadata.session_id` and `.thread_id` are corroborating
  aliases of the same CLI thread UUID. Require both, require canonical UUID
  strings, and require byte-for-byte equality.
- After corroboration, expose exactly one internal canonical
  `identity_hints={"session_id": <thread UUID>}`. Do not expose both aliases or
  any other raw metadata key.
- This client value is a namespace discriminator below the authenticated
  owner/key and server repository/route. It is not authentication, tenancy,
  authorization, accounting ownership, replay proof, or idempotency authority.
- Two mutually hostile processes must not share one Gateway bearer and expect
  the session namespace to isolate them; use separate Gateway keys/service
  identities. A future explicit Gateway-issued session negotiation is required
  only if hostile same-key isolation or a future client without this exact
  stable alias becomes a product requirement.

### Request/turn, replay, and idempotency

- `root_turn_id`, `turn_id`, `prompt_cache_key`, request/message/item IDs,
  timestamp, and nonce are not the Local Coding session.
- Gateway request ID and PostgreSQL reservation/ledger ownership remain one
  request's lifecycle facts. Do not claim session-level request deduplication.
- Signed replay remains exact body/method/path/query/identity/timestamp/nonce
  HMAC verification with process-local nonce TTL/LRU. A stable session neither
  grants nor weakens replay acceptance.

## Required implementation

### 1. Reproducible exact Codex session relationship evidence

- Extend the bounded exact 0.149 capture tool with a separate session evidence
  mode using one private `CODEX_HOME`/workspace and loopback synthetic Responses
  only. Verify literal `codex-cli 0.149.0`.
- Start session A, retain its CLI thread UUID only in memory, then invoke exact
  explicit `codex exec resume <thread UUID>` for A's second request. Start a
  separate session B under the same private installation. Do not use `--last`
  as proof of explicit session continuity.
- Before deleting raw values, prove only safe relations:
  - CLI thread ID, `session_id`, and `thread_id` are canonical UUIDs and equal
    on each request;
  - all three are equal across A1/A2;
  - session B differs while installation identity remains equal;
  - root/turn/cache/input-item facts are not accepted as session facts.
- Persist no raw values or hashes. Add a canonical sanitized relationship
  fixture containing only exact version/profile, selected source key name,
  alias/equality/type/canonicality booleans, same-session stability,
  cross-session difference, same-installation fact, rejected source categories,
  synthetic/no-provider transport facts, and cleanup.
- Preserve historical and v2 structural fixtures byte-for-byte. Increment the
  0.149 module version and bind it to the new relationship fixture/digest,
  which must reference the prior structural digest as provenance without
  rewriting it.
- Any missing alias, non-canonical UUID, disagreement, instability on explicit
  resume, or cross-session equality blocks implementation. Never infer from
  values, content/history, `--last`, IP, timing, connection, or workspace.

### 2. Exact module extraction and privacy

- Replace the `x-codex-*` pass-through extractor with exact v3 extraction:
  validate required `session_id` and `thread_id` aliases as canonical UUID
  strings and exact equals, then return only canonical `session_id`.
- `root_turn_id`, `turn_id`, `x-codex-installation-id`,
  `x-codex-window-id`, `x-codex-turn-metadata`, prompt-cache keys, input/item
  IDs, and all other values must never enter `identity_hints`.
- Missing, malformed, unequal, duplicate/ambiguous, control-bearing, URL-like,
  secret-looking, or over-bound aliases fail with one bounded module error
  before route/provider/reservation. Do not echo the field values.
- Continue validating and dropping the complete allowed client-metadata field
  in request policy. No raw metadata reaches normalized provider body, Local
  Coding, Qwen, persistence, hashes, logs, audit, metrics, exports, errors, or
  OAP evidence.
- Preserve candidate/tool behavior, exact pair, key/route gates, and default/
  0.147/other-client behavior.

### 3. Gateway-owned isolation in opaque derivation

- Narrow the core derivation input contract to exactly canonical
  `identity_hints.session_id`; reject any additional session/thread/turn/root
  hint rather than applying ordering or precedence.
- Require both authenticated `owner_id` and authenticated `gateway_key_id` UUID
  facts from `AuthenticatedGatewayKey`.
- Keep opaque principal derived from owner truth. Derive opaque session with a
  new explicit domain-separated internal derivation version over:
  `principal`, authenticated `gateway_key_id`, and corroborated Codex thread
  UUID. Keep repository derived from principal plus server-side
  `local_coding_repository_scope`; route remains the resolved route contract.
- The wire `signed_identity_v1` canonical header/HMAC contract remains
  unchanged because all four identity fields remain opaque. Document that this
  unmerged integration changes the internal derivation namespace and therefore
  causes a safe cache miss relative to earlier mock-only PR heads.
- Prove stability for same owner/key/session/repository/route and isolation for
  each changed owner, Gateway key, Codex session, repository, and route.
  Missing owner/key/session/repository/secret or malformed route fails closed.
- Static mode remains explicitly request-isolated/no-governed-rehydration and
  does not require signed identity. Do not add an unsigned fallback.

### 4. Accounting, failure, and signed transport proof

- Add focused PostgreSQL and mocked official-client evidence for at least two
  signed requests in session A plus one in session B. Same A requests must emit
  the same opaque session; B must differ; nonces/signatures/request IDs remain
  request-specific.
- Add a different-Gateway-key/same-owner/same-client-session case proving the
  opaque session differs and no Local Coding rehydration/cache namespace can
  cross the accounting credential boundary.
- Prove raw aliases and all excluded metadata are absent from provider body,
  Local Coding headers/body except the opaque derived session, ledger, audit,
  replay rows, logs, metrics, errors, and safe evidence.
- Success remains one ordinary `strict_bounded` reservation and terminal
  finalized ledger per request using provider-returned usage, zero pending
  counters, empty external facts, fence `none`, and no hosted fee/hold.
- Alias/session/key/repository negatives fail before provider and before
  reservation/ledger. Provider/signature/stream failures retain existing
  terminal accounting law. Session never acts as an idempotency key or external
  tool authority.

### 5. Documentation and Local 005-i handoff

- Update module, forwarding, Responses, security, accounting, and compatibility
  contracts with the identity model and threat boundary above. State that exact
  0.149 explicit resume is proven; `--last` is not the identity contract;
  client thread is a namespace below Gateway authority; same-bearer hostile
  session isolation is not claimed; Local/Gateway restart loses process-local
  rehydration/replay state safely.
- The report must contain only safe relationship booleans/key names, module
  version/digest, internal derivation version, unit/DB/mock evidence, cleanup,
  exact heads/checks, and limitations—never raw IDs/hashes.
- Keep Gateway PR #291 open. Publish the exact immutable head for Local Coding's
  prepared `005-i` full real Codex -> Gateway -> Local Coding -> Qwen acceptance.
  Do not perform protected Qwen/model traffic in this Gateway round.

## Exact allowed paths

```text
app/slaif_gateway/modules/clients/codex_0149.py
app/slaif_gateway/modules/servers/local_coding/identity.py
app/slaif_gateway/services/responses_gateway.py
scripts/capture_codex_protocol.py
tests/fixtures/codex/0.149.0/**
tests/unit/test_codex_client_modules.py
tests/unit/test_codex_protocol_capture.py
tests/unit/test_local_coding_server_module.py
tests/integration/test_codex_client_modules_postgres.py
tests/integration/test_local_coding_server_module_postgres.py
tests/e2e/test_openai_python_client_responses.py
docs/module-architecture.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/security-model.md
docs/accounting.md
docs/compatibility-matrix.md
oap/orders/155-e-codex-thread-namespace-and-key-bound-session.md
oap/reports/155-e-codex-thread-namespace-and-key-bound-session.md
oap/active
```

Use the narrowest subset. No schema/migration, new endpoint/header, Gateway
session store, route pair/contract, provider adapter, pricing, external-tool,
Compose, deployment, external-repository, release, or production change is
authorized.

## Required verification

- Exact official Codex 0.149.0 A1/explicit-A2/B relationship capture under one
  private installation, canonical sanitized fixture/digest, prior-fixture byte
  guards, raw privacy scan, and complete cleanup.
- Unit tests for alias canonicality/equality, exact single-hint output,
  old/new module metadata, excluded install/turn/root/cache/item facts, bounded
  safe errors, and unchanged non-0.149 behavior.
- Core tests for owner/key/session/repository/route isolation, deterministic
  same-session output, static mode, secret/route/missing-context negatives,
  exact signed bytes, and nonce/signature request variance.
- PostgreSQL no-side-effect negatives and ordinary finalized success for
  multiple sessions/keys; skipped DB tests are not a pass.
- Mocked official-client non-stream/SSE as affected, including no raw metadata
  forwarding/persistence and no external-tool facts.
- `python -m ruff check` on changed Python, `git diff --check`,
  `python scripts/check_documentation.py`, unchanged Alembic head, and final
  GitHub CI/CodeQL. Use focused tests; do not run the broad local suite.
- Report each command accurately. Pending/skipped/missing/not-run is not pass.

## Anti-false-positive acceptance

- Using `--last` alone, one request, or two new sessions as same-session proof
  fails. Explicit resume must retain the same CLI thread UUID.
- Accepting `session_id` without an equal canonical `thread_id`, returning both
  hints, or choosing by precedence fails.
- Treating the client thread UUID as authentication, tenancy, accounting,
  replay, or idempotency authority fails.
- Omitting authenticated `gateway_key_id` from the derived cache-session
  namespace fails cross-key isolation.
- Using root/turn/install/cache/item/request/content/connection/IP/timestamp or
  a generated per-request value as the stable session fails.
- A Gateway-issued session endpoint/header/cookie, Local-generated token, or
  protocol extension is out of scope because exact Codex 0.149 already provides
  a corroborated stable namespace. Future clients that do not must fail closed
  pending separate protocol design.
- Unit/mock success without exact CLI relationship capture and PostgreSQL
  success/no-side-effect evidence fails.
- Running Local 005-i/Qwen, modifying Local Coding, merging either PR, starting
  Objective 156, or claiming real composed/MVP/production qualification fails.

## Cross-repository merge gate

- This Gateway report is not Objective-155 acceptance. Local Coding 005-i must
  pin its exact report/implementation heads and run the full real composed
  acceptance before either integration PR merges.
- A passing Local 005-i may make Local Coding PR #7 mergeable without Gateway
  PR #291 already being merged; the tested exact open Gateway head is sufficient
  evidence and removes the prior circular dependency.
- After Local PR #7 merges, verify its merge contains the tested 005-i report
  head and original signed-contract head. Then recheck unchanged Gateway PR
  #291 report head, all required checks, reviews, scope, and mergeability before
  merging Gateway PR #291.
- Do not activate Objective 156 merely to repeat the same composition. Its inert
  proposal must be revised or retired after accepted 005-i evidence; any later
  post-merge smoke/release evidence is a separate deliberate decision.

## Setup, cleanup, and publication

- Routine exact-version private capture tooling and a disposable PostgreSQL
  test DB are authorized. No apt install, protected credential/Qwen/model call,
  public listener, or production mutation is authorized.
- Remove exact capture install/home/workspace/output/listener/log state and the
  disposable DB before report publication; verify absence. Preserve unrelated
  worktrees and protected services.
- Amend only PR #291. Do not create another PR, merge, or enable auto-merge.
- Commit this unchanged order and `oap/active` with implementation. Push all
  non-report commits and inspect final-head checks.
- Atomically publish exactly one immutable
  `oap/reports/155-e-codex-thread-namespace-and-key-bound-session.md` with
  literal implementation-head SHA and `Report publication commit: SELF`; the
  report commit must have that parent and change only the report file.
- Verify remote report head/topology before exact response FIFO `OK`. Coding
  agent never merges.
