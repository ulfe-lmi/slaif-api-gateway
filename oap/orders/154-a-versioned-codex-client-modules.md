# OAP Work Order — 154-a

PR mode: `CREATE_NEW_PR`
Base: `main @ 4b04d6519c11c684b2eac70dc1757c515d2ea4ab`
Branch: `oap/154-versioned-codex-client-modules`
Title: `obj154: move Codex protocols into versioned client modules`

## Objective and reason

Adopt Codex as a versioned client-module family instead of continuing to add
Codex-version branches to generic Responses core policy. Preserve the currently
qualified Codex 0.147 profile exactly, and capture/register Codex 0.149 as a
separate default-denied contract whose adapter-managed search declarations
cannot reach any current server module.

This objective addresses the client half of the Local Coding complaint without
implementing Local Coding or weakening hosted-tool policy. It must make future
Codex syntax/version changes client-module work while keeping authentication,
route selection, authority, PostgreSQL accounting, replay ownership, and
provider execution in the core.

## Verified current state

- Objective 153 merged as PR #289 at
  `4b04d6519c11c684b2eac70dc1757c515d2ea4ab`. Real Chat/Responses ingress uses
  the static `openai-default` client module and provider/facial dispatch uses
  the server registry. Client/server authority and registry-bypass guardrails
  are executable.
- No Objective 154 branch or PR exists. Unrelated open PRs #224 and #250 must
  not be changed.
- The canonical current Codex qualification is an exact 0.147.0 API-key
  Responses profile. Existing request-envelope, client-tool taxonomy,
  streaming/replay, compaction, profile and fixture behavior is implemented and
  must remain qualified without rewriting its immutable capture fixture/digest.
- Current Codex-specific constants and decisions remain spread through
  `responses_request_policy.py`, route capabilities, stream validation,
  profile/qualification/replay services, and tests.
- The Local Coding handoff and PR #7 report that Codex 0.149.0 emits top-level
  `function`, `custom`, `tool_search`, `web_search`, and in one configuration
  `namespace` declarations. Current Gateway policy correctly rejects hosted
  declarations before route resolution. The other repository retained only a
  bounded type/outcome vector, not a complete Gateway canonical fixture.
- Installed host Codex versions, user configuration, `~/.codex`, session JSONL,
  history, cache, auth stores, and prior captured content are untrusted and must
  not be searched or reused.
- Local Coding PR #7 remains an unmerged architecture input. No Local Coding
  server module or compatible Codex 0.149 pair exists in the Gateway.

## Required implementation

### 1. Extend the client-module contract safely

- Extend the Objective 153 client module contract with only the pure hooks
  needed for versioned Responses request classification/normalization and
  client-specific stream/profile facts. The module receives no database,
  provider, route, pricing, quota, Redis, audit, or public-auth service.
- Module output may contain canonical request data, bounded capability intents,
  adapter-managed declaration candidates, and untrusted identity hints. These
  are data/facts only and grant no authority.
- Core selects the client module from server-side Gateway key/profile metadata.
  Never select from User-Agent, arbitrary request field, client header, model
  name alone, or dynamic body heuristics.
- Unknown/malformed module IDs, versions, fixture digests, key/profile metadata,
  and unsupported client/server pairs fail before provider work and before
  quota reservation where current sequencing permits.
- Preserve a documented compatibility path for existing exact legacy Codex
  keys if they do not yet carry an explicit module ID. That path may derive
  only from the complete existing server-side Codex key policy/profile facts;
  it must not infer from client input and must not apply to 0.149.

### 2. Codex 0.147 module extraction

- Register an immutable client module such as
  `codex-0.147-responses-v1`, tied to the existing exact fixture digest,
  model/profile registry entry, request envelope, client-tool taxonomy,
  streaming event/replay/compaction contract, limits, and key/route gates.
- Move Codex-version-specific request constants, exact taxonomies, field-shape
  validation, declaration classification, identity-hint parsing, and stream
  profile selection behind that module or module-owned pure support files.
- Generic Responses core may retain reusable neutral primitives and call
  client-module hooks, but it must not remain the ownership point for a growing
  list of Codex-version literals/taxonomies.
- Do not alter the checked-in 0.147 fixture or digest. Existing Codex
  qualification/profile rendering, HMAC replay ownership, accounting, stream
  lifecycle, compaction, and privacy evidence must remain behavior-identical.
- Update the profile registry so the exact 0.147 profile declares its client
  module ID/version. Pair it only with the server-module categories already
  allowed by its current qualification contract; do not infer broader pairs.

### 3. Safe exact Codex 0.149 capture

- Obtain exact Codex CLI 0.149.0 only from the official OpenAI release/source
  distribution into an owner-only disposable directory. Verify exact raw
  `codex-cli 0.149.0` before capture and delete the binary/runtime afterward.
  If an exact trusted artifact cannot be obtained, stop before creating a
  fixture and report the blocker; do not substitute 0.149.1 or another version.
- Use a private repository-owned temporary `CODEX_HOME` and empty workspace,
  fake loopback Responses server, dummy synthetic Gateway token, no provider
  key, no model call, no network tool, no user config, no auth store/history/
  memory/rules/plugins/MCP/apps/browser/computer/search authority, and no host
  Codex/session/cache paths.
- Capture predetermined bounded variants needed to distinguish unavoidable
  Codex declarations from optional configuration. Retain raw request material
  only in bounded memory and discard it immediately.
- Commit only a canonical sanitized structural fixture and digest containing
  allowed field names/types/counts, exact declaration type and allowed-field
  shapes, tool-choice structure, pinned catalog/profile facts, and fixed safe
  findings. Do not retain prompts, outputs, descriptions, schemas/property
  names, grammar, arguments/results, IDs, paths, repository/session values,
  URLs, headers, credentials, or raw bodies.
- Cross-check official OpenAI Responses documentation only for authority class
  semantics: built-in tools remain distinct from client function/custom tools.
  Official API availability does not authorize Gateway forwarding.

### 4. Codex 0.149 default-denied module

- Register a distinct immutable client module such as
  `codex-0.149-responses-v1` tied to the new exact fixture digest.
- Validate only the exact bounded observed request envelope. Classify exact
  `web_search` and `tool_search` declaration shapes as
  `adapter_managed_codex_search` candidates. They are not canonical hosted-tool
  requests and do not set the existing external-tool policy/fence path.
- Continue to reject malformed/unknown fields, preview aliases, explicit
  `web_search`/`tool_search` choices, unsatisfiable required choices, provider
  URLs/auth/headers, MCP/connectors, file search, code interpreter, computer,
  image generation, hosted shell, background, and every other authority shape.
- Add no compatible server-module pair for 0.149 in this objective. Therefore a
  request selecting this module must fail closed at the exact pair/route gate
  before reservation/provider execution. The module may become executable only
  after Objective 155 adds a separately reviewed Local Coding server module and
  Objective 156 authorizes the exact pair.
- Do not strip or rewrite the candidates in the Gateway. The future Local
  Coding server contract owns downstream removal; Objective 154 only produces
  validated canonical candidate facts and proves default denial.

### 5. Operator/profile and privacy boundaries

- Expose module ID/version/digest only in safe profile/inspection/admin facts
  where current Codex qualification metadata is already shown. Do not add
  arbitrary editable module IDs to generic admin forms/imports.
- Key creation/profile rendering for current 0.147 must bind the exact module
  automatically from the server registry. 0.149 remains unavailable for normal
  key/profile creation until a later exact pair is qualified.
- Identity hints remain transient untrusted namespace input. Do not store,
  log, audit, export, hash, or forward raw installation/session/thread/turn/
  workspace metadata. Objective 155 owns trusted opaque identity derivation.

### 6. Architectural enforcement

- Extend module guardrails so Codex-version-specific fixture/taxonomy/tool-
  declaration constants live under `modules/clients/codex_*` or explicitly
  shared pure client-module support, not generic provider/server code.
- Client modules remain no-network/no-DB/no-Redis/no-provider/no-accounting.
- Add tests preventing the 0.149 candidate capability from appearing in the
  default/OpenAI 0.147 module, server modules, hosted-tool policy, or external-
  tool accounting code.

## Documentation

- Update `docs/module-architecture.md`, `docs/codex-compatibility.md`,
  `docs/responses-compatibility.md`, `docs/provider-forwarding-contract.md`,
  `docs/security-model.md`, and `docs/compatibility-matrix.md` as needed.
- Preserve current 0.147 qualification language.
- State 0.149 status exactly: structurally captured/module registered,
  default-denied, no compatible server pair, no provider/model/Qwen/Local
  Coding E2E, and no qualification.
- Note the official OpenAI Responses distinction between built-in and custom/
  function tools, while making clear that documentation does not grant runtime
  authority.

## Candidate paths

```text
app/slaif_gateway/modules/contracts.py
app/slaif_gateway/modules/clients/**
app/slaif_gateway/modules/servers/registry.py
app/slaif_gateway/services/responses_request_policy.py
app/slaif_gateway/services/responses_route_capabilities.py
app/slaif_gateway/services/responses_gateway.py
app/slaif_gateway/services/codex_profile_registry.py
app/slaif_gateway/services/codex_qualification.py
app/slaif_gateway/services/codex_replay_service.py
app/slaif_gateway/providers/streaming.py
app/slaif_gateway/schemas/policy.py
app/slaif_gateway/schemas/providers.py
app/slaif_gateway/cli/codex.py
app/slaif_gateway/api/admin.py
app/slaif_gateway/web/templates/routes/detail.html
scripts/capture_codex_protocol.py
scripts/verify_codex_profile.py
scripts/verify_codex_gateway_e2e.py
tests/fixtures/codex/0.149.0/**
tests/unit/test_module_architecture.py
tests/unit/test_responses_request_policy.py
tests/unit/test_responses_codex_envelope.py
tests/unit/test_responses_codex_client_tools.py
tests/unit/test_responses_codex_streaming_tools.py
tests/unit/test_responses_codex_multiturn_replay.py
tests/unit/test_responses_codex_compaction.py
tests/unit/test_codex_profile_registry.py
tests/unit/test_codex_qualification.py
tests/unit/test_codex_protocol_capture.py
tests/unit/test_v1_responses_quota.py
tests/e2e/test_openai_python_client_responses.py
docs/module-architecture.md
docs/codex-compatibility.md
docs/responses-compatibility.md
docs/provider-forwarding-contract.md
docs/security-model.md
docs/compatibility-matrix.md
oap/orders/154-a-versioned-codex-client-modules.md
oap/reports/154-a-versioned-codex-client-modules.md
oap/active
```

Use the narrowest actual subset and current equivalent test names. No migration,
provider factory/server implementation, pricing, accounting, Redis, Compose,
or configuration-template change is authorized.

## Required verification

- Exact fixture digest/structural reproducibility and host-path/privacy scans.
- Focused module architecture, current 0.147 profile/capture/request/tool/
  stream/replay/compaction/qualification tests.
- Focused 0.149 module positive structural and exhaustive negative authority/
  pair-denial tests.
- PostgreSQL Responses tests proving 0.147 behavior/accounting unchanged and
  0.149 pair denial creates no reservation/ledger/provider side effect; skipped
  PostgreSQL evidence is not a pass.
- Existing mocked official-client Responses E2E and isolated current 0.147
  Codex gateway E2E with no real provider.
- Ruff changed Python, `git diff --check`, documentation checker, focused docs
  tests, and one unchanged Alembic head inspection.
- Final GitHub CI/CodeQL on report head.

Do not run a real provider, Local Coding, Qwen, OpenCode, production Compose,
email, deployment, or broad local suite. No API key is required.

## Anti-false-positive acceptance

- Wrapping old core Codex functions while leaving version ownership and
  taxonomy literals in generic core does not complete extraction.
- Changing/replacing the immutable 0.147 fixture or silently mapping 0.149 to
  the qualified 0.147 profile fails.
- Capturing installed 0.149.1 as 0.149.0, using host user state, or retaining raw
  request/session/workspace content fails.
- Accepting 0.149 candidates globally, stripping them in Gateway, granting an
  OpenAI/OpenRouter/generic pair, or entering hosted-tool fence/accounting fails.
- A module unit test without real Responses handler/policy/route/no-side-effect
  evidence fails.
- Existing 0.147 behavior or privacy regression fails.

## Boundaries and non-goals

- No Local Coding server module, service Bearer, signed identity, exact-body
  signing, replay state, Qwen call, or composed pair.
- No OpenCode module.
- No hosted-tool execution, dynamic plugins, migration, provider/accounting
  rewrite, production data, deployment, release, certification, compliance,
  invoice, support, or SLA work.

## Publication and report duties

- Create exactly one non-stacked PR from current main; coding agent never merges
  or enables auto-merge.
- Commit this order and active selector unchanged.
- Publish one immutable `oap/reports/154-a-versioned-codex-client-modules.md`
  as the sole report-only commit. Record exact capture source/version/digest,
  module ownership moves, legacy behavior evidence, 0.149 default-denial and
  no-side-effect evidence, privacy scan, focused/PostgreSQL/E2E results, docs,
  skipped/not-run boundaries, PR/check state, and limitations.
- Verify report topology and remote head, then send exact `OK` to response FIFO.
