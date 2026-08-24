# OAP Work Order — 153-a

PR mode: `CREATE_NEW_PR`
Base: `main @ 05f7b6deddea3f742acba686fbeedc9088c4b057`
Branch: `oap/153-client-server-module-architecture`
Title: `obj153: adopt static client and server modules`

## Objective and reason

Adopt one clean, statically registered module architecture with distinct client
and server interfaces. Client modules decode versioned untrusted client
dialects into canonical Gateway request facts. Server modules translate
already-approved canonical requests into one reviewed upstream contract. The
Gateway core remains authoritative for authentication, effective policy,
routing, PostgreSQL quota/accounting, Redis controls, pricing, audit, privacy,
and failure behavior.

This foundation must be real production wiring, not interfaces used only by
tests. It must preserve all current behavior while making later Codex,
Local Coding, and OpenCode work module-local. The current facial-scoring native
module becomes the first concrete native server module under the new layout.

## Verified current state

- Objective 152 and PR #287 are terminal. Current `main` is
  `05f7b6deddea3f742acba686fbeedc9088c4b057`; real-provider verifier tooling is
  merged and live eight-flow qualification remains explicitly incomplete.
- There is no Objective 153 branch or PR. Unrelated open PRs are Dependabot
  #224 and #250; do not modify, merge, or reuse them.
- Current client-specific Responses behavior is spread across
  `responses_request_policy.py`, `responses_route_capabilities.py`,
  `responses_gateway.py`, stream validation, and Codex profile/replay services.
  Do not move Codex behavior in this objective; Objective 154 owns that
  extraction after this foundation merges.
- Native server-module behavior currently lives under
  `app/slaif_gateway/modules/`, with the reviewed `facial_scoring` adapter as
  the only registered native module. OpenAI/OpenRouter/generic transports live
  under `providers/`, and `providers/factory.py` selects them or delegates to
  the native module registry.
- Current facial-scoring behavior is a post-MVP, non-streaming Chat image
  adapter with fixed zero-EUR request pricing and the ordinary Gateway auth,
  policy, request/rate/concurrency, quota, revocation, expiry, audit, and
  privacy boundaries. It must not change here.
- Local Coding PR #7 is open in another repository. It and the complaint about
  Codex 0.149 are architecture inputs only; this objective must not consume its
  unmerged runtime contract, change that repository, or add Local Coding
  behavior.

## Required architecture

### 1. One module root, two unequal trust interfaces

Create an explicit internal layout under `app/slaif_gateway/modules/`:

```text
modules/
  contracts.py
  clients/
    base.py
    registry.py
    openai_default.py
  servers/
    base.py
    registry.py
    facial_scoring/
      adapter.py
      fixtures and manifest where currently packaged
```

Exact support filenames may follow repository style, but client and server
code must be visibly separated under this common root. Existing public import
paths may remain as thin compatibility re-exports where required; duplicate
implementations are forbidden.

Client modules and server modules are intentionally not symmetrical:

- a client module receives only the endpoint and untrusted validated-at-ingress
  mapping needed to normalize its protocol; it returns a content-free module
  identity plus canonical request data, bounded capability intents, and
  explicitly untrusted identity hints;
- a client module cannot authenticate, query databases, use Redis, select a
  provider/route, reserve quota, price, audit, perform HTTP, or grant authority;
- a server module receives only core-resolved provider/route facts and the
  canonical provider request after policy/admission; it returns existing safe
  provider response/stream/usage/failure types;
- a server module cannot authenticate a public key, mutate key/route policy,
  reserve/finalize quota directly, or receive the public Gateway bearer;
- the core, not either module, intersects client, key, route, provider, endpoint,
  capability, and accounting policy.

All module IDs and factories are static allowlists. Do not use `importlib`,
entry points, arbitrary dotted paths, admin-supplied classes, reflection-based
loading, package discovery, or a plugin marketplace/SDK.

### 2. Real default client-module wiring

- Define one immutable default client-module ID and version for ordinary
  OpenAI-compatible Chat Completions and Responses traffic.
- Invoke that module from the real Chat and Responses create entrypoints before
  the current endpoint policy layer. The module must produce a fresh canonical
  mapping/result without mutating the caller object and without logging or
  retaining request content.
- The current request-policy, route, quota, provider, stream, replay, and
  accounting services remain the owners of all existing behavior. The default
  module must not duplicate or bypass them.
- For Objective 153, the default module is selected only by core-owned default
  configuration. Do not add request/User-Agent heuristic selection or expose an
  arbitrary module identifier to clients. Objective 154 owns explicit
  versioned Codex key/profile/route selection.
- Unknown client IDs, duplicate registrations, unsupported endpoints, or a
  client/server pair absent from the static compatibility registry fail before
  provider construction and before any new side effect.

This is not satisfied by a factory test alone: focused gateway tests must prove
the actual Chat and Responses handlers call the default client module and then
continue through current policy/routing/accounting behavior.

### 3. Real server-module dispatch

- Make production provider construction resolve one static server-module
  descriptor before adapter creation. Built-in OpenAI, OpenRouter, and generic
  OpenAI-compatible transports may remain implemented in `providers/` as
  shared transport code, but their server descriptors/selection ownership live
  under `modules/servers/`.
- Move the facial-scoring implementation under
  `modules/servers/facial_scoring/` or make the new path the single
  implementation with compatibility re-exports from the old path. The static
  server registry must own its allowlisting.
- Preserve `get_provider_adapter(...)` as a compatibility/core entrypoint if
  useful, but it must delegate to the server-module registry; a parallel
  production factory is forbidden.
- Preserve exact provider slug/kind/base URL/secret env/timeout/retry validation
  and client-Authorization replacement. Unknown server/module/provider IDs
  remain fail closed.
- Preserve facial fixture packaging, hashes, dimensions, manifest provenance,
  and all current adapter/accounting/privacy behavior.

### 4. Static pair compatibility

- Represent supported client/server pairings in a finite server-owned or core-
  owned compatibility registry. The initial default client pairs only with the
  already supported built-in/generic/native server descriptors.
- A pair declaration is compatibility metadata only. It cannot enable an
  endpoint, model, route, provider, capability, hosted tool, pricing mode, or
  key permission.
- Module identity and selected pair may appear only as bounded low-cardinality
  safe diagnostics where current contracts permit; they must not cause request
  bodies, client metadata, tool schemas, images, prompts, outputs, or secrets to
  be stored/logged.

### 5. Architectural enforcement

Add focused import/AST/dependency tests that fail if:

- client modules import DB repositories/session code, Redis, HTTP clients,
  provider factories, accounting/quota/pricing/audit mutation services, or
  dynamic-loading libraries;
- server modules import public authentication or directly invoke Gateway
  quota/accounting repositories/services;
- module registries accept nonliteral/dynamic identifiers or duplicate IDs;
- Gateway production entrypoints bypass the selected client/server registry;
  or
- a compatibility re-export contains a second implementation.

Keep these tests narrow enough to permit schemas, settings, safe errors,
provider transport primitives, and shared pure validation helpers required by
the respective interface.

## Documentation requirements

- Add `docs/module-architecture.md` as the current internal architecture and
  contributor contract, with the flow:

  ```text
  client → client module → Gateway core → server module → upstream
  ```

- Explain that client syntax changes should normally remain client-module
  changes and upstream protocol changes server-module changes, while new
  authority/accounting semantics still require core review.
- Update `docs/README.md`, `docs/provider-forwarding-contract.md`,
  `docs/security-model.md`, and `docs/compatibility-matrix.md` only as needed to
  make the static architecture and unchanged current behavior discoverable.
- State explicitly that Codex 0.149, Local Coding, and OpenCode modules are
  planned follow-on work, not implemented by this objective.
- Preserve the concise public README; do not turn it back into an internal
  architecture catalog.

## Exact allowed task-authored paths

```text
app/slaif_gateway/modules/**
app/slaif_gateway/providers/factory.py
app/slaif_gateway/providers/openai.py
app/slaif_gateway/providers/openrouter.py
app/slaif_gateway/providers/openai_compatible.py
app/slaif_gateway/services/chat_completion_gateway.py
app/slaif_gateway/services/responses_gateway.py
app/slaif_gateway/schemas/providers.py
docs/module-architecture.md
docs/README.md
docs/provider-forwarding-contract.md
docs/security-model.md
docs/compatibility-matrix.md
pyproject.toml
tests/unit/test_module_architecture.py
tests/unit/test_module_provider.py
tests/unit/test_facial_scoring_adapter.py
tests/unit/test_provider_factory.py
tests/unit/test_v1_chat_completions_forwarding.py
tests/unit/test_v1_responses_quota.py
tests/integration/test_facial_scoring_gateway_postgres.py
tests/e2e/test_openai_python_client_chat.py
tests/e2e/test_openai_python_client_responses.py
oap/orders/153-a-static-client-server-module-architecture.md
oap/reports/153-a-static-client-server-module-architecture.md
oap/active
```

Use the narrowest subset. Existing files may have slightly different focused
test names; if an exact listed test path does not exist, identify and use the
current equivalent without inventing a duplicate suite. No migration or
configuration-template change is authorized.

## Required verification

- `git diff --check`.
- Ruff on all changed Python files.
- Focused module architecture, registry, factory, facial, real Chat/Responses
  production-handler, provider-header, and privacy tests.
- Existing focused PostgreSQL facial-scoring accounting/auth/revocation/expiry
  tests using a disposable `TEST_DATABASE_URL`; skipped PostgreSQL evidence is
  not a pass.
- Focused official-client mocked Chat and Responses E2E proving the default
  module path without real providers.
- `python scripts/check_documentation.py` and focused documentation inventory/
  contract tests.
- `alembic heads` is inspection-only and must remain the existing single head;
  do not run migrations or add a migration.
- Final GitHub CI and CodeQL on the report head.

Do not run broad local suites, real providers, Local Coding, Qwen, Codex,
OpenCode, production Compose, email, or external discovery. Normal GitHub CI
remains required.

## Anti-false-positive acceptance

- Pure interfaces plus test-only implementations do not pass; real Chat,
  Responses, provider-factory, and facial dispatch must use the registries.
- A generic no-op hook that cannot fail unknown/incompatible module selection
  does not pass.
- Moving files while leaving client/server-specific branching in an alternate
  production path does not pass.
- Dynamic imports, client-selected module names, User-Agent authority, or
  module-owned auth/policy/quota/accounting fail the objective.
- Any current request acceptance/rejection, OpenAI/OpenRouter header/body,
  facial response/accounting, privacy, retry, or error-shape regression fails.
- A module pair declaration must not grant hosted tools, external authority,
  endpoints, models, providers, pricing, or key permissions.
- Green CI alone does not prove architecture ownership; inspect production
  callsites and dependency guardrails.

## Boundaries and non-goals

- No Codex client extraction or 0.149 compatibility.
- No Local Coding server module, signed identity, service token, HMAC vector,
  replay state, Qwen call, or cutover.
- No OpenCode capture/module.
- No hosted tool, MCP, connector, web/file search, shell, computer, image-
  generation, background, or provider-authority expansion.
- No dynamic plugin framework, external package API, module marketplace, or
  arbitrary third-party code.
- No schema migration, release, deployment, real credential, production data,
  certification, compliance, invoice, support, or SLA work.

## Publication and report duties

- Create exactly one PR on the named branch from exact current `main`; never
  stack on another feature branch.
- Commit this strategic order and `oap/active` unchanged with the objective
  implementation/governance commit set.
- Never merge or enable auto-merge.
- Publish exactly one immutable
  `oap/reports/153-a-static-client-server-module-architecture.md` as the sole
  path in the final report-only commit. Record exact base/PR/branch/heads,
  production callsites, moved/re-exported paths, pair registry, focused test and
  PostgreSQL evidence, docs, security/privacy/accounting review, skipped/not-run
  evidence, and limitations. Use `Report publication commit: SELF`.
- Verify report topology and remote PR head, then send exact `OK` to the
  response FIFO and resume the control FIFO.
