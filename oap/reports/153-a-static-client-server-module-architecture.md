# OAP report — 153-a static client and server module architecture

- Objective: \`153-a\`
- Active selector: \`153-a\`
- Base: \`main @ 05f7b6deddea3f742acba686fbeedc9088c4b057\`
- PR: [#289](https://github.com/ulfe-lmi/slaif-api-gateway/pull/289)
- Branch: \`oap/153-client-server-module-architecture\`
- Order/selector commit: \`15ee1f4\`
- Initial implementation commit: \`8069ef5\`
- Final implementation head: \`ea198ac\`
- Report publication commit: SELF

## Outcome

Objective 153-a is implemented as production wiring, not a test-only hook.
The Gateway now uses the following flow for ordinary Chat Completions and
Responses create requests:

\`\`\`text
client → openai-default client module → Gateway core → static server module → upstream
\`\`\`

The Gateway core remains the authority for authentication, effective policy,
routing, PostgreSQL quota/accounting, Redis controls, pricing, audit, privacy,
and failure behavior.

## Production callsites and module paths

- \`services/chat_completion_gateway.py\` invokes the immutable
  \`openai-default\` client module before the existing Chat policy layer.
- \`services/responses_gateway.py\` invokes the same client module before the
  existing Responses policy layer.
- \`providers/factory.py\` resolves a static server descriptor and finite client/
  server pair before building an adapter; it no longer constructs provider
  adapters through a parallel native-module path.
- \`modules/clients/\` contains the pure client protocol, default normalizer,
  and immutable registry. It imports no database, Redis, HTTP, provider,
  quota, accounting, pricing, audit, or dynamic-loading code.
- \`modules/servers/registry.py\` owns literal descriptors and factories for
  OpenAI, OpenRouter, generic OpenAI-compatible, and facial-scoring servers.
  Pair declarations are compatibility metadata only.
- The facial-scoring implementation moved to
  \`modules/servers/facial_scoring/\`; the former
  \`modules/facial_scoring/\` path is only a compatibility re-export. Fixture
  packaging, hashes, dimensions, manifest provenance, fixed zero-EUR request
  pricing, auth, accounting, privacy, retry, and error behavior remain
  unchanged.
- \`modules/base.py\` and \`modules/__init__.py\` retain immutable compatibility
  symbols for existing imports; production dispatch is owned by the server
  registry.

Unknown client/server IDs, unsupported endpoints, duplicate/dynamic registry
changes, and absent client/server pairs fail closed. No request-selected module
ID, User-Agent heuristic, arbitrary dotted path, \`importlib\`, entry point,
reflection loader, package discovery, admin-supplied class, plugin marketplace,
or third-party module SDK was added.

## Security, privacy, and accounting review

Client modules cannot authenticate, use PostgreSQL or Redis, choose a provider
or route, reserve quota, price, audit, perform HTTP, or grant authority. Server
modules receive only core-resolved safe provider facts and cannot receive the
public Gateway bearer or directly mutate key, policy, quota, or accounting
state. Canonical client mappings are deep-copied and are not retained by the
module.

Module identity and pair metadata are low-cardinality static facts. The module
architecture adds no request-body, prompt, output, image, tool-schema,
credential, bearer, or secret persistence/logging. Existing provider header
replacement, diagnostics, retry, privacy, and accounting boundaries remain
owned by the existing core/transport services.

Codex 0.149, Local Coding, and OpenCode remain planned follow-on work.
No hosted-tool, external-authority, endpoint, model, provider, pricing, key
permission, migration, deployment, production-data, release, certification,
compliance, invoice, support, or SLA capability was added.

## Verification evidence

All local verification explicitly unset \`OPENAI_API_KEY\`,
\`OPENAI_UPSTREAM_API_KEY\`, \`OPENROUTER_API_KEY\`, \`DATABASE_URL\`,
\`TEST_DATABASE_URL\`, and \`RUN_UPSTREAM_TESTS\` except where an explicitly
generated disposable \`TEST_DATABASE_URL\` was supplied.

Passed focused evidence:

- \`git diff --check\`.
- \`python scripts/check_documentation.py\` (\`DOCUMENTATION_CHECK=OK\`,
  79 files).
- Project-rule Ruff checks on every changed Python path.
- Focused module architecture, module/provider registry, provider factory,
  facial adapter, Chat/Responses forwarding and quota, provider header and
  streaming, redaction/privacy, documentation inventory, documentation drift,
  and product-scope tests.
- Focused PostgreSQL facial-scoring adapter/qualification, module-provider
  foundation, and provider-diagnostics tests on a user-owned temporary TCP
  PostgreSQL cluster and explicitly prefixed disposable databases. Four
  focused facial/module tests and two provider-diagnostics tests passed; all
  generated databases were dropped and the cluster was stopped.
- Focused official OpenAI-client mocked Chat and Responses tests passed with
  all functional assertions, including Gateway-to-upstream Authorization
  replacement, request body preservation, response shape, and PostgreSQL
  accounting. The local cache lacked the pinned \`openai==2.41.0\` wheel and
  cached \`respx\` counted its intentional localhost pass-through route as
  uncalled; a narrow in-process test-harness workaround ignored only that
  pass-through bookkeeping. The upstream-route and accounting assertions were
  retained.
- \`alembic heads\` inspection reported the existing single head
  \`0024_quota_reservation_accounting_facts\`; no migration was run or added.

The first implementation-head CI run exposed the existing OpenAI/OpenRouter
provider-kind compatibility case and two dependent diagnostics failures.
The final implementation head \`ea198ac\` restores built-in provider-slug
dispatch while keeping generic/native selection strict. The rerun passed all
ten required checks:

- Analyze (javascript-typescript)
- Analyze (python)
- Analyze Python
- CodeQL
- Docker Compose smoke
- Documentation hygiene
- OpenAI-compatible E2E tests
- Playwright browser smoke
- PostgreSQL integration tests
- Unit, lint, and migration head

CI evidence is repository verification, not a production certification or
provider/model qualification.

## Scope and topology

The branch was created directly from exact current \`main\`; no feature branch
was stacked, rebased, squashed, or merged. The final report commit must have
\`ea198ac\` as its first parent and must change only this report path.
The selector/order bytes remain identical to the strategic checkout:

- \`oap/active\` SHA-256:
  \`bea02661e2e537844952ce6c23569a1811ee0fb248a0230ad6b9d427d0f0434c\`
- \`oap/orders/153-a-static-client-server-module-architecture.md\` SHA-256:
  \`8b91161974a78a8e59e03141bfd05057335a0f1f1061db1622b0669ce4a6d447\`

No real provider request, real credential, external discovery, Local Coding,
Qwen, Codex, OpenCode, email, deployment, release, or production-data action
occurred in this objective.
