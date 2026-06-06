# Responses Compatibility Contract

Status: limited foundation implemented on current `main`.

This document defines the RC2-beta support boundary for Responses API work.
Current support is deliberately narrow: stateless, text-only
`POST /v1/responses` with string input or bounded text-only input item arrays,
non-streaming JSON, typed SSE streaming, bounded non-streaming structured text
output through `text.format`, and local/client-side function tools. It has no
hosted tools, MCP/connectors, provider-side storage, background mode, previous
response or conversation state, or multimodal input/output.

## Supported Endpoint

The first implemented endpoint is:

- `POST /v1/responses`

Unsupported Responses routes remain unsupported until separate implementation
and tests add them.

Implemented request fields for the first slice:

- `model`
- `input` as a text string or bounded text-only message/input item array
- `instructions` as optional text
- `max_output_tokens`
- `temperature`
- `top_p`
- bounded `metadata`
- `stream` omitted, `false`, or `true` when the resolved route explicitly
  advertises Responses streaming support
- `store` omitted or `false`
- `text.format` as plain text, JSON object mode, or bounded JSON schema
  structured output
- `tools` with local function-tool entries only
- `tool_choice` as `none`, `auto`, `required`, or a named local function choice
- `service_tier` omitted or `auto`

If `store` is omitted, SLAIF injects `store=false` before provider forwarding so
the gateway remains stateless even when an upstream default would store
responses. If `max_output_tokens` is omitted, SLAIF injects the existing default
output cap. Streaming uses typed Responses SSE events such as
`response.created`, `response.output_text.delta`, `response.completed`, and
`error`; SLAIF does not translate Responses streams into Chat Completions
chunks.

Structured text output is a text-output constraint, not a tool or hosted
provider-side authority. JSON object mode uses
`text.format={"type":"json_object"}` and requires explicit
`capabilities.responses.json_mode=true`. JSON schema structured output uses
`text.format={"type":"json_schema","name":...,"schema":...}` with optional
`description` and `strict`, and requires explicit
`capabilities.responses.structured_outputs=true`. JSON schemas are forwarded
only inside this explicit `text.format` container, are capped, counted in the
admission-time input estimate, and are not stored or logged. Structured
`stream=true` requests are intentionally rejected in this slice; plain text
Responses streaming remains supported when the route advertises streaming.

Responses input item arrays are accepted only for stateless text message input.
Supported item shapes are simple message objects such as
`{"role":"user","content":"..."}` and explicit message items such as
`{"type":"message","role":"user","content":[{"type":"input_text","text":"..."}]}`.
Supported roles are `user`, `assistant`, `system`, and `developer`; content may
be a non-empty text string or a bounded list of `input_text` content parts.
Function-call items, reasoning/stateful items, hosted-tool items, and
image/file/audio content parts are rejected before Redis rate limiting, pricing
lookup, quota reservation, or provider forwarding. String-only
`function_call_output` items are supported as ordinary stateless input for local
function-tool follow-up requests; image/file outputs in tool-result items remain
rejected. Input item arrays use the same Responses text/stateless route
capability as string input. They compose with plain text streaming,
non-streaming structured `text.format`, and local function tools; structured
streaming and function-tool streaming remain rejected.

Responses local function tools are supported only as caller-side intent. SLAIF
forwards bounded function definitions shaped as
`{"type":"function","name":...,"parameters":...}` with optional `description`
and `strict` when the resolved route sets
`capabilities.responses.function_tools=true`. Function names, descriptions,
per-tool schemas, total tool schema bytes, and tool counts are capped. A named
`tool_choice` must reference a declared function in the same request. SLAIF
does not execute functions, does not add a special tool billing category, and
does not police downstream application behavior after a model returns a local
function-call item. Function definitions and string tool outputs are ordinary
input material for admission estimates; final accounting still uses provider
usage/cost once.

The first slice supports OpenAI Responses forwarding to `/v1/responses` when
the selected route explicitly advertises Responses text/stateless capability
and a `/v1/responses` pricing row exists. Streaming additionally requires
`capabilities.responses.streaming=true` and a streaming-capable route.
OpenRouter Responses forwarding, including streaming, is implemented only for
explicitly configured `/v1/responses` OpenRouter routes; OpenRouter support
remains beta/stateless and is not enabled by model allowlist alone.

## First Supported Mode

SLAIF starts with a stateless mode:

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

- Endpoint and model permission do not imply capability permission.
- Local function tools require explicit route/model
  `capabilities.responses.function_tools=true` metadata. Endpoint/model
  permission alone does not enable them.
- Function tools are supported only as caller-side intent because execution
  remains in the caller's application instead of inside the provider.
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

Current Chat Completions policy already applies the same fail-closed boundary
for implemented `/v1/chat/completions`: local function tools are allowed as
client-side behavior, non-streaming local custom tools are allowed only behind
explicit route capability and ordinary token accounting, while hosted/provider-side tools, MCP/connectors,
`web_search_options`, search-specific models, `background=true`, and
`external_web_access` are denied before provider forwarding. A Chat Completions
field registry also rejects unknown top-level fields, non-default service
tiers, streaming custom tools, streaming audio output, and unsupported broader
multimodal media-response content until those features have explicit policy,
pricing/accounting, forwarding, and tests. Chat Completions image input, inline
file input, audio input to text output, and non-streaming audio output are
separate route-enabled Chat Completions features and do not implement image
generation, `/v1/files`, hosted file search, retrieval, `/v1/audio/*`, Realtime,
or any Responses behavior. Chat Completions multiple choices are a separate bounded
request-shape feature that requires explicit `chat_multiple_choices` route
metadata and does not implement or imply any Responses behavior. This hardening
is separate from the stateless Responses text foundation.
The Chat Completions multimodal/audio/file evidence and roadmap are documented
separately in
[`chat-completions-multimodal-investigation.md`](chat-completions-multimodal-investigation.md);
that document does not change the planned Responses API boundary.

## Accounting Model

The existing reserve-before-provider-call model remains mandatory:

1. Authenticate gateway key.
2. Check endpoint/model/provider/tool policy.
3. Estimate input, output, tool-call, and fixed request cost.
4. Reserve PostgreSQL hard quota before provider forwarding.
5. Forward to the selected provider after reservation.
6. Finalize actual usage and cost from provider usage metadata.

For streaming Responses, SLAIF reserves before opening the provider stream,
forwards typed SSE events without storing streamed deltas, and finalizes once
from provider usage on the completed response event. The `response.completed`
event is held until usage-backed finalization succeeds. If an upstream provider
also emits `data: [DONE]`, SLAIF does not forward it as a normal success marker
before finalization; it is emitted only after the completed event on successful
finalization. Missing completed-event usage is not treated as zero cost; the
reservation is released through the streaming failure path and the client
receives a safe typed `error` event instead of a normal terminal success marker.

Current Chat Completions already uses admission-time budget checks plus
post-call spend accounting. Successful Chat Completions calls finalize actual
usage even when actual tokens or cost exceed the reservation, record safe
reservation-overrun and cost-source metadata, and rely on negative-balance
lockout for subsequent calls. This hardening does not implement
`/v1/responses` or `/v1/completions`, and it does not add multimodal/audio/file
pricing.

Responses input item text and item wrappers are included in the normal
admission-time input estimate. They do not create a new billing category; final
accounting still uses provider-reported usage/cost once.

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

Usable Responses policies require key templates. Durable template records and
immutable revisions now exist for reviewed calibration-derived Chat Completions
policy snapshots; Responses-specific template policy remains future work.

Template requirements:

- templates are versioned/snapshotted;
- a future key created from a template records template and revision metadata;
- editing a template never silently mutates existing keys;
- applying a template update to existing keys is a separate audited workflow;
- future workflows should let organizers create a test key from a template
  before issuing workshop keys;
- future bulk key creation can reference a template revision instead of
  duplicating every policy field per row.

See `docs/key-templates.md` for the current template contract and future
template-to-key workflow.

## Usage Tracking And Calibration Keys

Calibration keys let operators turn real organizer Chat Completions usage into
safer participant limits. A semi-trusted organizer, teacher, workshop lead, or
foreman can receive a relatively lenient calibration key, run the planned
seminar or workflow, and let an admin derive a stricter key template from the
observed usage window. Responses-specific calibration/template policy remains
future work.

The workflow is advisory until an admin confirms a template or key creation:

1. Create a lenient calibration key for a trusted organizer.
2. Run the representative workflow.
3. Select a source key and time window, such as the last week.
4. Review observed request, token, tool, and cost usage.
5. Choose a multiplier such as 1.5x, 2x, 3x, or a custom value.
6. Generate a proposed template with stricter per-key and per-request limits.
7. Let the admin edit assumptions before creating a template or bulk keys.

SLAIF now records a Chat Completions-first subset of safe operational metadata
in `usage_profiles` after successful accounting finalization. Trusted
calibration keys are also available for trusted organizers/admins: they are real
gateway keys with short validity and a small request limit, and they run through
normal authentication, routing, provider-secret isolation, PostgreSQL
accounting, usage ledger, usage profiling, and audit behavior. Their broad
discovery mode can observe routed Chat Completions capability needs, but they
are not participant keys and do not enable Responses API.

The table is the first persistence foundation for recommendations; it is
advisory and not invoice-grade billing truth. Admins can now generate a
preview-only calibration usage summary and strict participant-policy proposal
from CLI or admin web by selecting a trusted calibration key, time window, and
multiplier. After review, admins can create a durable template revision from the
proposal. That template creation does not create participant keys, mutate
existing key policy, or update routes/pricing. Admins can create one normal key
from a selected immutable revision, but bulk participant-key generation remains
future work. Future Responses work must extend the same safe metadata boundary
rather than storing request or response content.

Recommendation workflows need safe operational metadata such as:

- gateway endpoint path;
- provider and sanitized provider endpoint host/path;
- requested model and resolved upstream model;
- input, output, total, cached, and reasoning/thinking token counts when exposed
  by provider usage;
- tool call counts by type;
- safe function-tool names when available;
- provider-reported and gateway-calculated cost fields when available;
- request counts, per-request maxima, and bounded-overrun assumptions.

SLAIF must not store prompts, completions, messages, raw request bodies, raw
response bodies, raw tool payloads, raw chain-of-thought, provider keys,
plaintext gateway keys, encrypted payloads, nonces, password hashes, session
tokens, email bodies, query strings, URL fragments, credentials, signed URLs, or
bearer tokens for this workflow. Exact URL storage must be sanitized to gateway
endpoints and provider host/path only.

OpenAI exposes an input-token counting endpoint for Responses-compatible
payloads, including request shapes with tools and schemas. Provider final usage
can also expose input, output, cached, and reasoning token counts. SLAIF should
use those capabilities where available, but it must not assume every provider
exposes every tool metric, cost field, cached-token count, or reasoning-token
count. Missing provider details should be shown as assumptions in the
recommendation preview.

Derived templates can include:

- request count limits;
- input, output, reasoning, and total token limits;
- tool-call limits by type and safe function name;
- per-request maxima;
- allowed endpoints, models, and providers;
- Responses tool policy;
- maximum single-request cost and bounded-overrun estimates.

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

## Required Tests

The stateless text-only foundation is implemented with:

- request policy unit tests;
- route capability unit tests;
- provider adapter tests for OpenAI and OpenRouter Responses forwarding;
- endpoint allowlist and pipeline-ordering tests;
- PostgreSQL-backed mocked official OpenAI Python client E2E coverage.

Tool-enabled or stateful Responses support remains future work until these are
present and green:

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
