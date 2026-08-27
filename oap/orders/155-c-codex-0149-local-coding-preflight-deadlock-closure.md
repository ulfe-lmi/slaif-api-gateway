# OAP Work Order — 155-c

PR mode: `AMEND_EXISTING_PR`
PR: `#291`
Branch: `oap/155-local-coding-signed-server-module`
Base: `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`
Current remote head: `c68fa511141a0c21d420e7a94100f717e674553f`

## Objective and reason

Break the verified cross-repository acceptance deadlock without creating
Objective 156 early or weakening tool authority.

Local Coding Objective `005-g` attempted the exact no-live preflight against
Gateway PR #291 and exact Codex CLI 0.149.0. Its fresh disposable capture
observed top-level `function`, `custom`, `tool_search`, and `web_search`
declarations. Gateway PR #291 rejects the observed `tool_search` declaration
in the 0.149 client normalizer and has no exact
`codex-0.149-responses-v1` -> `local-coding-v1` compatibility pair, so the
preflight correctly stopped before PostgreSQL, Docker, listeners, or Qwen.

Gateway Objective 155 cannot merge until Local Coding PR #7 is accepted and
merged; Local Coding Objective 005 cannot finish acceptance until Gateway
publishes this correction; and Objective 156 cannot start until Objective 155
is terminal. Amend the existing Objective-155 PR with only the minimum
capture, pair, policy, tests, and documentation needed for Local Coding
`005-h` to resume its disposable cross-repository acceptance run.

## Verified starting state

- Canonical Gateway `main` remains
  `7ffce834915b74809109e8b579d8541cdcfa9df7`.
- Gateway PR #291 is OPEN, non-draft, MERGEABLE/CLEAN, with no auto-merge. Its
  remote head is immutable 155-b report commit
  `c68fa511141a0c21d420e7a94100f717e674553f`; first parent is implementation
  head `eac9c6354e19fdfa8574dc799fa5f1395382756f`; the report commit changes only
  `oap/reports/155-b-endpoint-secret-and-core-identity-containment.md`.
- All ten Gateway report-head checks are successful: unit/lint/migration,
  PostgreSQL integration, OpenAI-client E2E, Playwright, Compose,
  documentation hygiene, and all CodeQL/analysis jobs.
- Gateway 155-a/b exact-byte transport, Responses-create-only containment,
  secret-role separation, opaque core identity derivation, PostgreSQL failure
  law, and pinned fake-Qwen conformance remain accepted.
- Gateway's historical exact 0.149 fixture observes only `web_search`, so its
  current module correctly rejects unobserved `tool_search` and remains
  pairless. Do not rewrite that historical capture as though it observed a
  different envelope.
- Local Coding PR #7 is OPEN, non-draft, MERGEABLE/CLEAN at immutable 005-g
  report head `cd1a16cbddc4ff7e1ad2b2769fc1311479f0dc97`; its first parent is
  transcript implementation head
  `e080e27264b203c8a55a840078fc63aaf5c9e07d`; its `test` check is successful.
  Original pinned contract/report head
  `356be8345dd71d6fddf829278651d18e485731d4` remains an ancestor.
- Local Coding 005-g's exact Codex 0.149.0 capture recorded safe counts
  `function=5`, `custom=1`, `tool_search=1`, `web_search=1`, then stopped before
  live setup. No Gateway code, protected Qwen state, or production state was
  changed.
- The Local and Gateway fixture files are deliberately different artifacts:
  Gateway uses provenance wrappers whose embedded `source_fixture_sha256`
  identifies the raw Local fixture. Raw byte equality between wrapper and
  source is not the contract.

## Required implementation

### 1. Exact new Codex 0.149 capture evidence

- Reproduce the 005-g shape using exact official Codex CLI 0.149.0 in a fresh,
  private, disposable `CODEX_HOME` and workspace against a loopback synthetic
  Responses capture endpoint. Verify literal version output
  `codex-cli 0.149.0` before capture.
- Use no host Codex home/history/session/cache, no real provider/model/Qwen,
  and no reusable credential. Bound the attempt and remove all temporary
  binaries/runtime/profile/workspace/capture state afterward.
- Preserve the existing historical 0.149 fixture unchanged. Add a new
  canonical, sanitized structural fixture/variant for the newly reproduced
  envelope and bind the updated 0.149 module contract to its literal digest.
  If module metadata changes, increment its explicit module version; never
  silently reuse old version/digest metadata for changed accepted shapes.
- The new fixture may contain only safe structure: exact client version,
  method/path, field names/types, declaration types/counts/field-name sets,
  neutral tool-choice class, capture/cleanup facts, and qualification status.
  It must not contain prompts, outputs, tool descriptions, schema/property
  names, arguments/results, IDs, paths, URLs beyond the fixed endpoint,
  headers, credentials, raw bodies, or host state.
- Derive accepted candidate types and exact allowed field shapes from the new
  capture in tests. Do not infer `tool_search` fields from its name, the Local
  handoff, another Codex version, or a moving installation. If exact 0.149.0
  reproduction does not observe a complete safe shape, report the blocker and
  do not grant it.

### 2. Exact adapter-managed candidates, never hosted authority

- Update only the versioned Codex 0.149 client module so exact captured
  top-level `web_search` and `tool_search` declarations are classified as
  adapter-managed candidates.
- Validate the exact captured field set/value classes for each candidate.
  Unknown fields, aliases, preview/versioned names, malformed values, nested
  search declarations, MCP/connectors, URLs, authorization, headers, secrets,
  or any other provider-authority marker fail closed.
- Neutral absent/`auto` choice may accompany candidates. An explicit choice
  of `web_search` or `tool_search`, a required choice that becomes unsafe, or
  an unknown structured choice must fail before route/provider/reservation.
- Preserve ordinary captured `function`, `custom`, and bounded `namespace`
  declarations and client-side call/output linkage under existing independent
  Codex key/route gates. Do not broaden generic Responses tools.
- Candidate declarations remain transient in the canonical provider body and
  must reach only the exact Local Coding server adapter for its reviewed
  `responses-tool-policy-v1` removal. Gateway must not execute or silently
  strip them, treat them as OpenAI hosted search, acquire an external-tool
  fence/hold, charge hosted-search per-call pricing, grant provider authority,
  or persist/log/audit/export their content.

### 3. One exact static client/server pair

- Add exactly one compatibility entry:
  `codex-0.149-responses-v1` -> `local-coding-v1`.
- Do not pair Codex 0.149 with OpenAI, OpenRouter, generic
  `openai-compatible`, facial scoring, or any other server module. Do not pair
  any other client to Local Coding beyond already accepted entries.
- Selection still requires server-side key metadata matching the exact 0.149
  module ID/version/new fixture digest and a resolved `openai_compatible`
  provider route containing the exact valid `local-coding-v1` contract.
  Client headers, model names, provider slug/display name, or request fields
  cannot select or widen the pair.
- A mismatched/missing/malformed route contract, old module version/digest,
  wrong server/provider kind, unsupported endpoint, or ambiguous route must
  reject before provider work and before PostgreSQL reservation/ledger effects.
- Local Coding remains Responses-create/stream only. Input-token count,
  compact, stored-response lifecycle, Conversations, Audio, Embeddings,
  Realtime, Chat, and every other operation remain rejected before unsigned
  transport.

### 4. Core policy and accounting containment

- Introduce the narrowest core plumbing needed for a statically selected
  client module to pass its already shape-validated candidate facts through
  generic request policy. Do not hard-code Codex version behavior into neutral
  accounting, pricing, provider, or external-tool primitives.
- Module-supplied candidate facts are non-authoritative until the exact static
  client/server pair and route contract pass. The final pair/route gate must
  occur before Redis/provider/quota side effects.
- Prove exact-pair success uses ordinary bounded Responses reservation and
  finalization: one public request, one reservation, one terminal ledger
  outcome, provider-returned usage, zero pending reservation, and no external
  fence/hold/tool-fee facts.
- Prove wrong pair/route, explicit candidate choice, malformed candidate,
  missing key gates, quota rejection, and provider/signature failure preserve
  existing no-side-effect or terminal failure law as applicable.
- Preserve provider-secret substitution, exact signed body bytes, service/
  signing/derivation/public/Qwen credential separation, PostgreSQL accounting
  truth, no default content retention, and safe bounded errors.

### 5. Fixture provenance rule

- Keep Local Coding's raw fixtures and Gateway's provenance-wrapped copies as
  separate immutable artifacts. Verify each Gateway wrapper's embedded
  `source_fixture_sha256` equals the literal raw Local source digest and verify
  the reviewed semantic vector fields, rather than requiring wrapper/source
  files to be byte-identical.
- Do not modify Local Coding PR #7 or fabricate a new upstream digest. If the
  current source/provenance facts disagree, stop and report the exact mismatch.

### 6. Cross-repository resume handoff

- Do not perform the protected Qwen/full live cross-repository acceptance in
  this Gateway round. Publish a fully green immutable Gateway head containing
  the corrected module metadata, capture digest, exact pair, focused/DB/mock
  evidence, and limitations so the Local Coding strategic model can activate
  its prepared `005-h` resume order against that literal head.
- The 155-c report must explicitly enumerate the new capture facts, module
  version/digest, exact pair, negative pairs, candidate authority behavior,
  fixture provenance checks, PostgreSQL accounting evidence, all final-head
  checks, and the exact Local Coding 005-g head used as blocker evidence.

## Exact allowed paths

```text
app/slaif_gateway/modules/contracts.py
app/slaif_gateway/modules/clients/codex_0149.py
app/slaif_gateway/modules/clients/registry.py
app/slaif_gateway/modules/servers/registry.py
app/slaif_gateway/services/responses_gateway.py
app/slaif_gateway/services/responses_request_policy.py
scripts/capture_codex_protocol.py
tests/fixtures/codex/0.149.0/**
tests/fixtures/local_coding/**
tests/unit/test_codex_client_modules.py
tests/unit/test_codex_protocol_capture.py
tests/unit/test_module_architecture.py
tests/unit/test_local_coding_server_module.py
tests/unit/test_provider_factory.py
tests/unit/test_responses_request_policy.py
tests/unit/test_v1_responses_quota.py
tests/integration/test_codex_client_modules_postgres.py
tests/integration/test_local_coding_server_module_postgres.py
tests/e2e/test_openai_python_client_responses.py
docs/module-architecture.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/security-model.md
docs/accounting.md
docs/compatibility-matrix.md
oap/orders/155-c-codex-0149-local-coding-preflight-deadlock-closure.md
oap/reports/155-c-codex-0149-local-coding-preflight-deadlock-closure.md
oap/active
```

Use the narrowest subset. No schema, migration, dependency/lockfile, Compose,
deployment, external-repository, release, or production change is authorized.

## Required verification

- Exact Codex 0.149.0 no-provider disposable capture, canonical fixture digest,
  fixture self-consistency, privacy scan, and complete cleanup evidence.
- Focused 0.149 client normalization tests for both captured candidates,
  function/custom/namespace preservation, neutral choice, exhaustive negative
  authority/shape/choice cases, old metadata rejection, and fresh metadata
  selection.
- Static architecture tests proving the single new exact pair and exhaustive
  denial of every other 0.149 server pair.
- Focused request-policy/gateway tests proving candidates reach only the exact
  Local Coding adapter, are not classified as hosted execution, and mismatches
  fail before policy/provider/reservation as required.
- PostgreSQL integration with a safe disposable `TEST_DATABASE_URL` proving
  exact-pair success reservation/finalization and all named zero-side-effect/
  no-pending/no-fence negatives. A skipped database test is not a pass.
- Mocked official OpenAI-client Responses E2E for exact 0.149 metadata and
  exact Local Coding route, non-streaming and typed SSE as affected, with
  deterministic synthetic provider usage and no real model/provider.
- Re-run pinned Local Coding fake-Qwen conformance only if changed transport or
  fixture plumbing affects that boundary; never follow a moving dependency
  branch.
- `python -m ruff check` on changed Python, `git diff --check`,
  `python scripts/check_documentation.py`, unchanged Alembic head, and final
  GitHub CI/CodeQL. Use focused local tests; do not run the broad local suite.
- Report every command as PASSED/FAILED/SKIPPED/NOT RUN/BLOCKED. Missing,
  skipped, pending, cancelled, and not-run checks are not passes.

## Anti-false-positive acceptance

- Adding the pair without a new exact 0.149.0 capture and strict
  fixture-derived `tool_search` shape fails.
- Rewriting the historical fixture, accepting a handoff-only/type-only shape,
  or silently retaining its old module version/digest fails.
- Allowing candidates for the default/0.147 client, any non-Local-Coding
  server, or a malformed/missing Local route contract fails.
- Gateway stripping the candidates, executing them, entering hosted-tool
  fence/accounting, charging a web-search fee, or granting provider authority
  fails.
- Relying on raw byte equality between Local source fixtures and Gateway
  provenance wrappers fails.
- Mock-only unit evidence without PostgreSQL reservation/finalization and
  official-client E2E fails.
- Performing the protected Qwen/live 005-h acceptance, modifying Local Coding,
  adding general pair/plugin machinery, or claiming composed/live/
  production qualification in this round fails.

## Setup, authority, and publication

- Routine private capture tooling and a disposable PostgreSQL test database
  are authorized under repository safety rules. No apt-based PostgreSQL
  installation, production/protected credential, real provider, real Qwen,
  public listener, or external service mutation is authorized.
- Amend only Gateway PR #291. Do not create another PR, merge, or enable
  auto-merge. Local Coding PR #7 remains read-only.
- Commit this activated order and `oap/active` unchanged with the implementation
  commit set. Push all implementation commits and inspect checks before report.
- Atomically publish exactly one immutable
  `oap/reports/155-c-codex-0149-local-coding-preflight-deadlock-closure.md`.
  Record the literal implementation-head SHA and
  `Report publication commit: SELF`; the final report-only commit must have
  that implementation head as first parent and change only the report file.
- Verify the report commit is the remote PR #291 head before sending exact
  two-byte `OK` to `response.fifo`. Coding agent never merges.
