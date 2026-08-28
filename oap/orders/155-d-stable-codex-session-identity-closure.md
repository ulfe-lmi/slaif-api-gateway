# OAP Work Order — 155-d

PR mode: `AMEND_EXISTING_PR`
PR: `#291`
Branch: `oap/155-local-coding-signed-server-module`
Base: `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`
Current remote head: `c0094e478b83d33a52eb82a2ba9c8677e6af4a6e`

## Objective and reason

Close the exact Gateway-side stable-session identity defect found by Local
Coding Objective `005-h`, without inventing identity from per-turn or
installation-wide metadata.

Local Coding 005-h proved that Gateway 155-c now accepts the exact Codex 0.149
`tool_search`/`web_search` candidates and selects only the exact
`codex-0.149-responses-v1` -> `local-coding-v1` pair. Its mandatory signed-route
preflight then stopped before Docker, PostgreSQL, Gateway/Local Coding
listeners, or Qwen inference because `Codex0149ResponsesClientModule` exposes
only `x-codex-*` values through `identity_hints`. The Local Coding signed
identity boundary requires one stable session/thread hint; it correctly fails
closed when none is available.

Amend the same Gateway PR with an evidence-derived session identity contract
that is stable across multiple requests in one exact Codex session and isolated
across separate sessions under the same installation. Do not merely rename a
per-turn value, reuse an installation identifier, weaken signed identity, or
perform the protected composed acceptance owned by Local Coding `005-i`.

## Verified starting state

- Canonical Gateway `main` remains
  `7ffce834915b74809109e8b579d8541cdcfa9df7`.
- Gateway PR #291 is OPEN, non-draft, MERGEABLE/CLEAN with no auto-merge at
  immutable 155-c report head
  `c0094e478b83d33a52eb82a2ba9c8677e6af4a6e`; its first parent is
  implementation head `02670e3275ff57850aeaa9bc8aae4ed3c8e2f124`, and the
  report commit changes only
  `oap/reports/155-c-codex-0149-local-coding-preflight-deadlock-closure.md`.
- All ten Gateway report-head CI/CodeQL/PostgreSQL/E2E/Compose/documentation
  checks are successful. The exact fresh raw 0.149 request passes the
  registered version-2 normalizer and its module-owned policy; both adapter
  candidates stay non-hosted and ordinary strict-bounded accounting passes.
- Gateway historical 0.149 fixture
  `responses-structural.json` and v2 fixture
  `responses-structural-v2.json` are immutable at their reported digests.
- The current extractor in
  `app/slaif_gateway/modules/clients/codex_0149.py` returns only string-valued
  keys beginning `x-codex-`, while Local Coding derivation accepts one of
  `session_id`, `thread_id`, `turn_id`, or `root_turn_id` and rejects zero or
  multiple values.
- Local Coding PR #7 is OPEN, non-draft, MERGEABLE/CLEAN at immutable 005-h
  report head `6ee2a51aa7b03d4df46e0662d88cc33fd0ef7db8`; its first
  parent is transcript implementation head
  `d2093650ef61200d3ed6ff9516bfd73eb2675182`; its `test` check is successful.
  Original signed-contract head
  `356be8345dd71d6fddf829278651d18e485731d4` remains an ancestor.
- Local 005-h passed exact-head/provenance, 37 Local identity/tool tests, 430
  Gateway focused tests, exact raw capture, candidate/pair/policy negatives,
  credential-role checks, and protected vision health discovery. It made no
  model inference or product-code change and found no Local Coding defect.
- Local 005-h observed that the normalized exact 0.149 envelope exposed one
  transient `x-codex-*` hint and no usable standard session hint. It did not
  authorize guessing which raw field should represent a session.

## Required implementation

### 1. Exact same-installation session relationship capture

- Use exact official Codex CLI 0.149.0 in one fresh private disposable
  `CODEX_HOME` and bounded workspace against loopback synthetic Responses
  endpoints only. Verify literal version output `codex-cli 0.149.0`.
- Capture at least two model requests belonging to one Codex session A and at
  least one request belonging to a separate session B while retaining the same
  private installation/home. Use a safe synthetic tool roundtrip or another
  deterministic no-provider mechanism to produce multiple requests in A.
- Classify metadata only by safe key name, value type/bounds, and equality
  relationships. Identify exactly one source signal that:
  - is present and identical on both requests in session A;
  - differs for session B under the same installation;
  - is not the installation-wide identifier;
  - is not a per-turn/request identifier; and
  - remains a transient client namespace hint, not proof of external identity.
- Do not persist, print, log, hash, audit, or fixture-record raw metadata values,
  prompts, outputs, descriptions, schemas, arguments/results, IDs, paths,
  headers, credentials, request/response bodies, or session history.
- Preserve both existing 0.149 fixtures byte-for-byte. Add a separate canonical
  sanitized session-relationship fixture recording only exact CLI/profile
  version, source key name, safe value class/bounds, same-session stability,
  cross-session isolation, installation constancy, per-turn variance, no-model
  transport facts, and cleanup. Bind changed client semantics to an incremented
  module version and literal new fixture/contract digest.
- If no single source meets every relationship, or the capture is ambiguous,
  report BLOCKED and keep signed identity unavailable. Do not synthesize a
  session from request ID, model, route, owner, installation, turn, IP,
  workspace, timestamp, or random per-request data.

### 2. One canonical transient session hint

- Update only the 0.149 client module to consume the exact capture-proven raw
  source and expose exactly one canonical `identity_hints` entry suitable for
  Local Coding derivation, preferably `session_id` as the internal canonical
  name. Do not expose all raw metadata keys.
- Validate source type, non-empty/visible content, exact byte bound, and
  ambiguity before returning the canonical hint. Missing, malformed, control-
  bearing, over-bound, conflicting, per-turn-only, or installation-only input
  must produce no usable signed session or fail the module safely before
  provider/reservation.
- Do not forward the raw hint, alternate metadata values, or canonical raw
  value to Local Coding/Qwen. Only the existing HMAC-derived opaque session
  header may cross the signed server boundary.
- Do not persist, log, audit, export, metric-label, digest, or expose raw or
  canonical session hints. Existing safe request/session identifiers used for
  unrelated Gateway operations must not silently become Local Coding identity.
- Keep default, Codex 0.147, OpenAI/OpenRouter, generic, facial, and other
  client/server behavior unchanged. Client input cannot select the extractor or
  claim another session.

### 3. Stability and isolation proof through the core boundary

- Prove through `Codex0149ResponsesClientModule` and
  `_build_local_coding_server_context` that two requests in session A with
  different turn/request facts produce the same opaque Local Coding `session`,
  while session B under the same installation produces a different opaque
  `session`.
- Prove the installation identifier alone cannot create or collapse sessions;
  per-turn values alone cannot create a stable session; and multiple/conflicting
  candidate sources fail closed.
- Retain owner, repository binding, route, derivation-secret, static-mode, and
  missing-context behavior from 155-b. Owner/repository/route changes must
  remain isolated independently of the session dimension.
- For signed mode, missing stable session context must still return bounded
  `local_coding_identity_unavailable` before Redis, provider, quota reservation,
  or ledger side effects. Do not add unsigned fallback or request-isolated
  rehydration claims.

### 4. Transport, privacy, and PostgreSQL evidence

- Add mocked official-client/Gateway coverage for at least two sequential
  signed requests in session A and a request in session B. Inspect only safe
  derived headers/relationships: session A opaque headers equal, session B
  differs, nonces/signatures remain request-specific, and raw metadata never
  reaches Local Coding request body/headers or provider observations.
- Prove successful requests remain ordinary `strict_bounded` reservations with
  one terminal finalized ledger row each, zero pending counters, no external
  capabilities/destinations/provider/route facts, fence state `none`, no hosted
  fee/hold facts, and provider-returned usage finalization.
- Prove missing/ambiguous/per-turn/installation-only negative cases create no
  provider call, reservation, or ledger row. Verify logs/audit/ledger/metrics/
  errors contain none of the raw session, installation, turn, metadata, prompt,
  tool, secret, signature, or canonical-byte values.
- Preserve exact-byte signing, service/signing/derivation/public/Qwen secret
  separation, Responses-create-only adapter scope, PostgreSQL accounting truth,
  and no default content retention.

### 5. Cross-repository resume handoff

- Do not run Docker, protected Qwen, Local Coding listener, or full composed
  acceptance in this Gateway round. Local Coding `005-i` owns that exact run.
- Publish a fully green immutable Gateway head that records the session source
  key name and relationship booleans, module version/digest, safe extraction
  law, core stability/isolation, negative cases, DB/privacy evidence, cleanup,
  and exact Local 005-h blocker head. Never record raw values or hashes.
- Keep Gateway PR #291 open. Local Coding PR #7 remains read-only and must not
  merge until its own 005-i evidence is accepted.

## Exact allowed paths

```text
app/slaif_gateway/modules/contracts.py
app/slaif_gateway/modules/clients/codex_0149.py
app/slaif_gateway/modules/clients/registry.py
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
oap/orders/155-d-stable-codex-session-identity-closure.md
oap/reports/155-d-stable-codex-session-identity-closure.md
oap/active
```

Use the narrowest subset. No schema, migration, dependency/lockfile, route
pair, provider adapter, pricing, external-tool, Compose, deployment,
external-repository, release, or production change is authorized.

## Required verification

- Exact Codex 0.149.0 same-installation, same-session-two-request, and
  different-session relationship capture; canonical sanitized fixture,
  literal digest, privacy scan, and complete cleanup.
- Fixture tests proving both older 0.149 artifacts remain byte-identical and the
  new session fixture is derived only from safe relationship facts.
- Focused module tests for stable source extraction, canonical single-hint
  output, module version/digest selection, missing/malformed/conflicting input,
  per-turn and installation negatives, and no raw retention/forwarding.
- Core Local Coding tests for same-session stability and independent owner,
  session, repository, and route isolation plus all 155-b negative/static cases.
- PostgreSQL integration and mocked official-client signed non-stream/SSE as
  affected, proving named success/failure accounting, no external facts, and
  raw identity privacy. Skipped DB tests are not a pass.
- `python -m ruff check` on changed Python, `git diff --check`,
  `python scripts/check_documentation.py`, unchanged Alembic head, and final
  GitHub CI/CodeQL. Use focused local tests, not the broad local suite.
- Report every command as PASSED/FAILED/SKIPPED/NOT RUN/BLOCKED. Missing,
  skipped, pending, cancelled, and not-run checks are not passes.

## Anti-false-positive acceptance

- Adding `session_id`/`thread_id` to the extractor without the exact two-request
  same-session and same-installation cross-session capture fails.
- Renaming `turn_id`, `root_turn_id` if it varies per turn, request ID,
  `x-codex-installation-id`, or another installation-wide value as session
  fails.
- A unit-only synthetic stability test without actual exact-Codex relationship
  evidence fails.
- Returning multiple raw identity hints and relying on downstream ordering or
  precedence fails; ambiguous values must not choose silently.
- Forwarding, storing, hashing, logging, auditing, exporting, or printing raw
  identity/session/turn/install values fails.
- Mock-only success without PostgreSQL no-side-effect/finalization and signed
  core-boundary evidence fails.
- Running Local 005-i/protected Qwen, modifying Local Coding, weakening signed
  mode, adding unsigned fallback, starting Objective 156, or claiming composed/
  live/production qualification fails.

## Setup, authority, cleanup, and publication

- Routine private exact-version capture setup and a disposable PostgreSQL test
  database are authorized under repository safety rules. No apt-based
  PostgreSQL install, protected credential, model/provider/Qwen inference,
  public listener, or production mutation is authorized.
- Remove exact capture homes/workspaces/binaries/listeners/logs and the
  disposable test database before report publication; independently verify
  absence. Leave the Gateway PR worktree clean except for intended commits.
- Amend only Gateway PR #291. Do not create another PR, merge, or enable
  auto-merge. Do not modify Local Coding PR #7.
- Commit this activated order and `oap/active` unchanged with implementation.
  Push all implementation commits and inspect final-head checks before report.
- Atomically publish exactly one immutable
  `oap/reports/155-d-stable-codex-session-identity-closure.md` with literal
  implementation-head SHA and `Report publication commit: SELF`. The report
  commit must have that implementation head as first parent and change only the
  report file.
- Verify the report commit is remote PR #291 head before sending exact two-byte
  `OK` to `response.fifo`. Coding agent never merges.
