# Responses Compatibility Contract

Status: not implemented on current `main`.

This document defines the intended RC2-beta support boundary for Responses API
work. It is a planning and implementation contract, not a statement that
`POST /v1/responses` currently works.

## Supported-First Endpoint

The planned first endpoint is:

- `POST /v1/responses`

Unsupported Responses routes remain unsupported until separate implementation
and tests add them.

## Planned First Supported Mode

RC2 should start with a stateless mode:

- no `background=true`
- no provider-side response storage or retrieval
- no `store=true`
- no `previous_response_id`
- no conversation/provider-side state
- no MCP/connectors
- no response delete, cancel, retrieve, or input-item listing

OpenAI documents Responses as supporting background mode, response storage,
conversation state, previous response IDs, and hosted tools. OpenRouter documents
its Responses beta as stateless. SLAIF should therefore fail closed on stateful
and background features until it has explicit ownership mapping, quota/accounting
semantics, and tests.

## Tool Support Policy

Responses tools must not be blindly passed through.

Rules:

- Tools must be explicitly allowed by key or key template.
- Function tools are the safest first supported class because execution remains
  in the caller's application instead of inside the provider.
- Web search may be supported only with explicit `max_tool_calls`, model/tool
  allowlists, provider allowlists, and cost-bound calculations.
- File search and code interpreter/container tools require explicit policy,
  pricing, data ownership, and audit treatment before implementation.
- MCP/connectors are excluded from RC2.
- Image generation, computer use, shell, hosted patch/application tools, and
  external MCP/connectors are excluded unless explicitly approved in a later
  contract.

OpenAI documents hosted tools including web search, file search, function
calling, remote MCP, code interpreter/container, computer use, image generation,
shell, tool search, and patch-style tools. RC2 must treat those as separate
security and cost surfaces, not as generic JSON passthrough.

## Accounting Model

The existing reserve-before-provider-call model remains mandatory:

1. Authenticate gateway key.
2. Check endpoint/model/provider/tool policy.
3. Estimate input, output, tool-call, and fixed request cost.
4. Reserve PostgreSQL hard quota before provider forwarding.
5. Forward to the selected provider after reservation.
6. Finalize actual usage and cost from provider usage metadata.

With tool-enabled Responses, a request that starts under a key limit may exceed
the remaining limit because the model can spend the bounded tool budget before
final usage is known. RC2 may allow this only when:

- the maximum possible single-request overrun is bounded by policy;
- the bound is displayed to admins before enabling the policy;
- the bound is stored or traceable with the key/template revision;
- after an overrun, PostgreSQL accounting blocks future requests until limits
  are restored, raised, or reset.

## Key Policy

Responses is default-off per key.

Required policy controls:

- explicit Responses-enabled checkbox
- endpoint allowlist entry for `/v1/responses`
- existing allowed model and provider checks
- allowed tool types
- model/tool-specific caps
- maximum input tokens
- maximum output tokens via `max_output_tokens`
- maximum built-in tool calls via `max_tool_calls`
- maximum single-request estimated cost in EUR
- explicit unsupported-field rejection for stateful/background features

Leaving Responses disabled must continue to reject `/v1/responses` before route
resolution, pricing, quota reservation, or provider forwarding.

## Key Templates

Usable Responses policies require key templates.

Template requirements:

- templates are versioned/snapshotted;
- a key created from a template records template and revision metadata;
- editing a template never silently mutates existing keys;
- applying a template update to existing keys is a separate audited workflow;
- organizers can create a test key from a template before issuing workshop keys;
- bulk key creation can reference a template revision instead of duplicating
  every policy field per row.

See `docs/key-templates.md` for the planned template contract.

## Pricing Catalog

Local pricing remains the quota/accounting source of truth.

Planned pricing behavior:

- OpenRouter price refresh may use OpenRouter model metadata where available.
- OpenAI pricing should remain curated/manual or imported through an operator
  confirmed preview workflow unless a stable official pricing API exists.
- Pricing refreshes are previewed, confirmed, and audited.
- Pricing refreshes never silently replace production pricing rows.
- Tool pricing fields must cover per-token, per-request, per-tool-call, and
  provider-specific usage where applicable.
- Admin UI must show assumptions used for worst-case cost calculations.

See `docs/pricing-catalog.md` for the planned pricing and bounded-overrun
contract.

## Explicit Unsupported Fields For RC2

RC2 must reject these before provider forwarding unless a later contract updates
the support matrix:

- `background=true`
- `store=true`
- `previous_response_id`
- `conversation`
- MCP/connectors
- response retrieval
- response deletion
- response cancellation
- response input-item listing
- image generation
- computer use
- shell or hosted patch/application tools

## Required Tests Before Marking Implemented

Responses support is not implemented until these are present and green:

- request policy unit tests;
- provider adapter tests for OpenAI and OpenRouter;
- PostgreSQL quota/accounting integration tests;
- bounded-overrun tests;
- tool allowlist tests;
- unsupported stateful/background field tests;
- streaming tests if Responses streaming is implemented;
- mocked official OpenAI Python client E2E tests;
- mocked OpenRouter E2E tests;
- dashboard key/template policy tests;
- Playwright browser smoke update;
- Docker/CI green.

## Reference Docs Checked For This Contract

- OpenAI Responses API reference:
  <https://platform.openai.com/docs/api-reference/responses>
- OpenAI tools guide:
  <https://developers.openai.com/api/docs/guides/tools>
- OpenAI web search tool guide:
  <https://platform.openai.com/docs/guides/tools-web-search>
- OpenAI file search tool guide:
  <https://platform.openai.com/docs/guides/tools-file-search>
- OpenRouter Responses API beta:
  <https://openrouter.ai/docs/api-reference/responses-api/overview>
- OpenRouter Responses create endpoint:
  <https://openrouter.ai/docs/api/api-reference/responses/create-responses>
