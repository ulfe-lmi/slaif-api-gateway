# Responses Compatibility Contract

Status: limited foundation implemented on current `main`.

This document defines the RC2-beta support boundary for Responses API work.
Current support is deliberately narrow: `POST /v1/responses` with text output,
string input or bounded input item arrays, optional user-message `input_image`
content parts for image input to text output, optional user-message
`input_file` content parts for file input to text output, non-streaming JSON,
typed SSE streaming for stateless requests, bounded non-streaming structured
text output through `text.format`, local/client-side function tools, and
non-streaming local/client-side custom tools. `store=false` remains the default
for create. `store=true` is supported only for non-streaming stored-response
create when the route explicitly enables stored Responses. Retrieve/delete are
ownership-checked proxy calls backed by safe local response-reference metadata.
Non-streaming `previous_response_id` is supported only for locally recorded,
active, same-key provider response references after provider/route compatibility
checks. Input-item listing is supported only for owned locally recorded
provider response references and is proxied without local input-item content
storage. Conversations are supported as owned provider-side state references
through `POST /v1/conversations`, owned metadata-only update, owned
retrieve/delete, owned conversation
item create/list/retrieve/delete proxying, and non-streaming
`POST /v1/responses` with a locally recorded owned `conversation` ID; SLAIF
stores only safe conversation reference metadata and never stores conversation
item content.
`POST /v1/responses/input_tokens` is implemented as a separate
provider-reported count endpoint for the same local input subset.
`POST /v1/responses/compact` is implemented as a bounded non-streaming
text-focused compaction endpoint with explicit endpoint permission, route
capability, endpoint-specific pricing, quota reservation, and provider-usage
finalization. These slices have no hosted tools, MCP/connectors, background
mode, `/v1/files` lifecycle,
audio input, audio output, image generation, file search,
cancel/response-list routes, or multimodal output. SLAIF does not store
compact input, output, or encrypted compaction content.

## Supported Endpoint

The first implemented endpoint is:

- `POST /v1/responses`
- `POST /v1/responses/input_tokens`
- `POST /v1/responses/compact`
- `GET /v1/responses/{response_id}`
- `DELETE /v1/responses/{response_id}`
- `GET /v1/responses/{response_id}/input_items`
- `POST /v1/conversations`
- `POST /v1/conversations/{conversation_id}`
- `GET /v1/conversations/{conversation_id}`
- `DELETE /v1/conversations/{conversation_id}`
- `POST /v1/conversations/{conversation_id}/items`
- `GET /v1/conversations/{conversation_id}/items`
- `GET /v1/conversations/{conversation_id}/items/{item_id}`
- `DELETE /v1/conversations/{conversation_id}/items/{item_id}`

Unsupported Responses routes remain unsupported until separate implementation
and tests add them.

Implemented request fields for the first slice:

- `model`
- `input` as a text string or bounded message/input item array
- `instructions` as optional text
- `max_output_tokens`
- `temperature`
- `top_p`
- bounded `metadata`
- `stream` omitted, `false`, or `true` when the resolved route explicitly
  advertises Responses streaming support
- `store` omitted, `false`, or non-streaming `true` when the resolved route
  explicitly advertises stored Responses support
- `previous_response_id` as a bounded string for non-streaming requests when it
  references a locally known, active, owned, provider-compatible Response
- `conversation` as a bounded string for non-streaming requests when it
  references a locally known, active, owned, provider-compatible Conversation
- `text.format` as plain text, JSON object mode, or bounded JSON schema
  structured output
- `tools` with local function-tool or custom-tool entries only
- `tool_choice` as `none`, `auto`, `required`, a named local function choice,
  or a named local custom choice
- `service_tier` omitted or `auto`

If `store` is omitted, SLAIF injects `store=false` before provider forwarding so
the gateway remains stateless even when an upstream default would store
responses. Explicit `store=true` requires `stream=false` and
`capabilities.responses.stored_responses=true`; it persists only safe provider
response reference metadata after a successful provider create response with an
ID. If `max_output_tokens` is omitted, SLAIF injects the existing default
output cap. Streaming uses typed Responses SSE events such as
`response.created`, `response.output_text.delta`, `response.completed`, and
`error`; SLAIF does not translate Responses streams into Chat Completions
chunks.

`POST /v1/responses/input_tokens` accepts the supported stateless local input
subset for counting only: `model`, `input`, `instructions`, `text`, local
function/custom `tools`, `tool_choice`, `parallel_tool_calls`, and `truncation`
(`auto` or `disabled`). It rejects create-only and stateful fields including
`stream`, `store`, `max_output_tokens`, `background`, `previous_response_id`,
`conversation`, and `reasoning`. The endpoint requires explicit key permission
for `/v1/responses/input_tokens`, a model route for `/v1/responses/input_tokens`,
and `capabilities.responses.input_token_count=true` in addition to
`responses.text=true` and `responses.stateless=true`. Image, file, function
tool, and custom tool inputs still require their existing explicit route
capabilities. The provider response is forwarded only when it has the official
shape `{"object":"response.input_tokens","input_tokens":...}`.

The input-token count endpoint does not create a Response, does not inject
`store=false`, does not inject or require `max_output_tokens`, does not reserve
generation quota, and does not create a normal generation usage ledger row. It
is a provider-reported metadata call for admission/planning compatibility.

`POST /v1/responses/compact` accepts a deliberately narrower text-focused
subset: `model`, required `input`, and optional `instructions`. The compact
input may be a non-empty string or a message item array with string content or
`input_text`/`output_text` content parts. Message `id`, `type=message`, and
bounded status metadata are preserved as inert provider payload fields when
supplied. Compact rejects `stream`, `store`, `background`, `conversation`,
`previous_response_id`, tools, hosted-tool fields, media/file/audio inputs,
file IDs, and unknown fields. It routes through `/v1/responses/compact`,
requires `capabilities.responses.compact=true`, uses endpoint-specific pricing,
reserves quota with `RESPONSES_COMPACT_DEFAULT_MAX_OUTPUT_TOKENS`, and
finalizes from provider usage. Provider compact responses without usage fail
safely and are not finalized as zero-cost success.

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

Responses input item arrays are accepted only for stateless message input.
Supported item shapes are simple message objects such as
`{"role":"user","content":"..."}` and explicit message items such as
`{"type":"message","role":"user","content":[{"type":"input_text","text":"..."}]}`.
Supported roles are `user`, `assistant`, `system`, and `developer`; content may
be a non-empty text string or a bounded list of `input_text` content parts.
User-message content arrays may also include bounded `input_image` parts shaped
as `{"type":"input_image","image_url":"...","detail"?:...}` when the resolved
route sets `capabilities.responses.image_input=true`. Supported image sources
are fully-qualified `http`/`https` URLs without embedded credentials or
fragments, and `data:image/png|jpeg|webp|gif;base64,...` data URLs. Supported
detail values are `auto`, `low`, `high`, and SDK-supported `original`; omitted
detail is omitted upstream so the provider default applies. SLAIF does not
fetch remote URLs, decode image pixels, rewrite image data URLs, store/log image
URLs or base64 payloads, or infer final billing from bytes. Image URL/data URL
material is included in conservative admission estimates, while final
accounting uses provider usage/cost once.
User-message content arrays may include bounded `input_file` parts shaped as
`{"type":"input_file","file_url":"https://..."}` when the resolved route sets
`capabilities.responses.file_input=true`. File URL input must be a fully
qualified HTTPS URL without embedded credentials or fragments and with an
allowed extension. User-message content arrays may also include inline file
data shaped as
`{"type":"input_file","filename":"document.pdf","file_data":"data:application/pdf;base64,..."}`.
Inline file data requires a safe basename filename with an allowed extension
and a configured base64 data URL MIME type. SLAIF does not fetch file URLs,
parse, OCR, index, extract text from, or store/log file URLs, filenames, data
URLs, or base64 payloads. File URL/data URL material is included in
conservative admission estimates, while final accounting uses provider
usage/cost once. `input_file.file_id` remains unsupported until `/v1/files`
ownership and provider-file lifecycle are implemented.
Function-call items, reasoning/stateful items, hosted-tool items, and
audio content parts are rejected before Redis rate limiting, pricing lookup,
quota reservation, or provider forwarding. `input_image.file_id` remains
unsupported until `/v1/files` ownership and provider-file lifecycle are
implemented. String-only
`function_call_output` items are supported as ordinary stateless input for local
function-tool follow-up requests; image/file outputs in tool-result items remain
rejected. Input item arrays use the same Responses text/stateless route
capability as string input; image input additionally requires
`capabilities.responses.image_input=true`, and file input additionally requires
`capabilities.responses.file_input=true`. They compose with plain text streaming,
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

Responses local custom tools are supported only as caller-side intent for
stateless non-streaming requests. SLAIF forwards bounded custom tool
definitions shaped as `{"type":"custom","name":...}` with optional
`description` and optional `format` when the resolved route sets
`capabilities.responses.custom_tools=true`. Omitted `format` preserves the
OpenAI default of unconstrained text. Supported explicit formats are
`{"type":"text"}` and
`{"type":"grammar","syntax":"lark"|"regex","definition":...}`. Custom tool
names, descriptions, grammar definitions, total custom format bytes, and tool
counts are capped. A named custom `tool_choice` must reference a declared
custom tool in the same request. SLAIF does not execute custom tools, inspect
or store generated custom tool input, add a special billing category, or police
downstream application behavior after a model returns a local custom-tool call
item. String-only `custom_tool_call_output` items are supported as ordinary
stateless input for caller-managed follow-up requests; content arrays,
image/file outputs, and `custom_tool_call` input items remain rejected.
`stream=true` with custom tools or custom-tool outputs is rejected in this
slice.

The first slice supports OpenAI Responses forwarding to `/v1/responses` when
the selected route explicitly advertises Responses text/stateless capability
and a `/v1/responses` pricing row exists. Streaming additionally requires
`capabilities.responses.streaming=true` and a streaming-capable route.
OpenRouter Responses forwarding, including streaming, is implemented only for
explicitly configured `/v1/responses` OpenRouter routes; OpenRouter support
remains beta/stateless and is not enabled by model allowlist alone.

## Stored Response Lifecycle

The first stateful lifecycle slice is intentionally limited:

- `store=true` is accepted only for non-streaming `POST /v1/responses`;
- the resolved route must advertise
  `capabilities.responses.stored_responses=true`;
- `stream=true` with `store=true` is rejected;
- successful stored create persists only a safe local response reference after
  the provider returns an `id`;
- `GET /v1/responses/{response_id}` and
  `DELETE /v1/responses/{response_id}` are proxied only after the authenticated
  gateway key owns an active local reference for that provider response ID;
- missing, non-owned, or locally deleted references return an OpenAI-shaped
  404 and are not proxied upstream.
- `GET /v1/responses/{response_id}/input_items` is proxied only after the same
  local ownership check and only when the stored route advertises
  `capabilities.responses.list_input_items=true`;
- input-item listing supports only validated `after`, `limit`, `order`, and a
  conservative `include` allowlist, and forwards only validated query
  parameters to the owning provider;
- SLAIF returns the provider list response without storing or inspecting
  input-item content;
- `previous_response_id` is accepted only for non-streaming create requests
  after the referenced provider response ID resolves to an active local
  reference owned by the authenticated gateway key;
- `previous_response_id` requires
  `capabilities.responses.previous_response_id=true`;
- if `store=true` is combined with `previous_response_id`, the route must also
  advertise `capabilities.responses.stored_responses=true`, and the new
  provider response reference is persisted after a successful provider response;
- unknown, non-owned, deleted, provider-mismatched, or route-incompatible
  previous response IDs return an OpenAI-shaped 404 and are not proxied
  upstream.
- `POST /v1/conversations` creates an empty provider conversation only;
  initial items/metadata are rejected in this first slice so SLAIF does not
  validate or store conversation item content;
- successful conversation create persists only a safe local conversation
  reference after the provider returns an `id`;
- `GET /v1/conversations/{conversation_id}` and
  `DELETE /v1/conversations/{conversation_id}` are proxied only after the
  authenticated gateway key owns an active local reference for that provider
  conversation ID;
- `POST /v1/responses` with `conversation` is accepted only for non-streaming
  requests after the provider conversation ID resolves to an active local
  reference owned by the authenticated gateway key;
- `conversation` requires `capabilities.responses.conversations=true` on the
  resolved Responses model route and cannot be combined with
  `previous_response_id`;
- unknown, non-owned, deleted, provider-mismatched, or route-incompatible
  conversation IDs return an OpenAI-shaped 404 and are not proxied upstream.
- `POST /v1/conversations/{conversation_id}/items` accepts only bounded text
  message items and rejects hosted-tool, tool-output, media, file, audio, and
  provider-side authority markers;
- `GET /v1/conversations/{conversation_id}/items` supports only validated
  `after`, `before`, `limit`, `order`, and conservative `include` query
  parameters;
- `GET /v1/conversations/{conversation_id}/items/{item_id}` supports only the
  same conservative `include` query parameter, and delete supports no query
  or body payload;
- all conversation item endpoints first require an active local conversation
  reference owned by the authenticated gateway key, use the provider
  conversation ID from that reference, and return OpenAI-shaped 404 without
  provider proxying for unknown, non-owned, deleted, or incompatible
  conversations.

The local response reference stores provider response ID, gateway key/owner
metadata, provider, requested/upstream model, endpoint, route/status/timestamps,
and safe provider request metadata only. SLAIF does not store prompts,
completions, raw request bodies, raw response bodies, tool schemas, tool
inputs/outputs, image/file URLs, media payloads, provider keys, plaintext
gateway keys, token hashes, or one-time secret material.

The local conversation reference stores provider conversation ID, gateway
key/owner metadata, provider, endpoint, route/status/timestamps, and safe
provider request metadata only. SLAIF does not store conversation items,
prompts, completions, raw request bodies, raw response bodies, tool schemas,
tool inputs/outputs, image/file URLs, media payloads, provider keys, plaintext
gateway keys, token hashes, or one-time secret material.

Retrieve/delete/input-item listing are control-plane proxy calls: they do not
reserve output quota or create normal generation usage ledger rows. Stored
create and `POST /v1/responses` with `conversation` remain ordinary generation
requests and use the existing reservation/finalization accounting path.
Conversation create/update/retrieve/delete and conversation item create/list/retrieve/delete
are control-plane proxy calls and do not reserve output quota or create normal
generation usage ledger rows. If a
provider returns no response ID for `store=true`, SLAIF fails safely instead of
claiming retrievable state. If provider conversation create returns no
conversation ID, SLAIF fails safely instead of claiming owned state.

Still unsupported:

- `background=true`
- MCP/connectors
- streaming `previous_response_id`
- streaming `conversation`
- `previous_response_id` on compact
- response cancel or response listing

OpenAI documents Responses as supporting background mode, response storage,
conversation state, previous response IDs, and hosted tools. OpenRouter documents
its Responses beta as stateless. SLAIF enables only the owned retrieve/delete,
owned input-item listing, owned previous-response, owned conversation, and
owned conversation item proxy slices
above and continues to fail closed on other stateful and background features
until explicit ownership mapping, quota/accounting semantics, and tests exist.

## Tool Support Policy

Responses tools must not be blindly passed through.

Rules:

- Endpoint and model permission do not imply capability permission.
- Local function tools require explicit route/model
  `capabilities.responses.function_tools=true` metadata. Endpoint/model
  permission alone does not enable them.
- Local custom tools require explicit route/model
  `capabilities.responses.custom_tools=true` metadata. Function-tool
  capability and Chat Completions custom-tool capability do not enable
  Responses custom tools.
- Image input requires explicit route/model
  `capabilities.responses.image_input=true` metadata. Chat Completions image
  capability does not enable Responses image input.
- File input requires explicit route/model
  `capabilities.responses.file_input=true` metadata. Chat Completions file
  capability and Responses image-input capability do not enable Responses file
  input.
- Function tools are supported only as caller-side intent because execution
  remains in the caller's application instead of inside the provider.
- Custom tools are also caller-side intent; SLAIF forwards definitions and
  preserves provider-returned custom-tool call items but never executes a tool.
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
request is finalized as estimated interrupted usage when token-bearing output
was already observed, and the client receives a safe typed `error` event
instead of a normal terminal success marker.

Streaming live-burn margin for Responses typed SSE is implemented for the
currently supported stateless text-output streaming subset. The governance
milestone is [`streaming-live-burn-margin.md`](streaming-live-burn-margin.md).
SLAIF estimates visible `response.output_text.delta` text only, discards the
text after counting, and may intentionally stop the upstream stream when the
estimated request cost or token burn crosses the configured Responses
streaming live-burn cutoff. The threshold-crossing delta is withheld rather
than forwarded. Provider final usage remains authoritative when it arrives
before an abort. Missing usage, provider error after observed output, and
client disconnect after observed output finalize as estimated interrupted usage
rather than normal success, and this feature does not enable background mode,
cancel, response listing, Responses audio, or stateful streaming with
`store=true`, `previous_response_id`, or `conversation`.

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
policy snapshots and for a safe local/stored Responses policy summary. The
Responses template policy surface is provenance metadata for implemented local
capabilities only; it is not a raw request/tool-schema store and it does not
bypass route/model capability enforcement.

Template requirements:

- templates are versioned/snapshotted;
- a key created from a template records template and revision metadata;
- editing a template never silently mutates existing keys;
- applying a template update to existing keys is a separate audited workflow;
- organizers can create exactly one normal key from a selected immutable
  revision before issuing workshop keys;
- future bulk key creation can reference a template revision instead of
  duplicating every policy field per row.

For `/v1/responses`, a template revision may carry
`template_snapshot.responses_policy` with version 1, allowed local capabilities
(`text`, `stateless`, `streaming`, `json_mode`, `structured_outputs`,
`function_tools`, `custom_tools`, `image_input`, `file_input`,
`input_token_count`, `stored_responses`, `previous_response_id`,
`list_input_items`, `compact`, `conversations`, `conversation_items`), allowed local
tool types (`function`, `custom`), an empty hosted-tool allowlist, and explicit
false storage, background, and multimodal-output flags. `stored_responses` and
`previous_response_id`, `list_input_items`, and `compact` are only safe
capability
summaries for non-streaming stored create, owned retrieve/delete/input-item
listing, owned previous-response chaining, owned conversation references,
owned conversation item proxying, and bounded text-focused compact;
they do not permit raw response IDs from user traffic, prompts, completions,
input items, compact input/output, encrypted compaction content, or response
content in template metadata. Template-to-key creation copies that
sanitized summary into gateway-key metadata. Hosted tools, MCP/connectors,
conversation state, background, raw image URLs/data, raw file URLs/names/data/base64,
raw tool definitions, schemas, generated tool inputs, and tool outputs remain
out of scope for template metadata and are rejected.

See `docs/key-templates.md` for the current template contract and remaining
future bulk/template update workflows.

## Usage Tracking And Calibration Keys

Calibration keys let operators turn real organizer Chat Completions usage into
safer participant limits. A semi-trusted organizer, teacher, workshop lead, or
foreman can receive a relatively lenient calibration key, run the planned
seminar or workflow, and let an admin derive a stricter key template from the
observed usage window. Responses-specific detailed usage profiling remains
future work, while template revisions can already carry the safe stateless local
Responses policy summary described above.

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
future work. Current Responses template metadata is limited to the safe
stateless local policy summary; future Responses usage-derived recommendations
must extend the same safe metadata boundary rather than storing request or
response content.

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
- streaming `previous_response_id`
- `conversation`
- MCP/connectors
- response cancellation
- response listing
- image generation
- computer use
- shell or hosted patch/application tools

## Required Tests

The local/stored Responses foundation is implemented with:

- request policy unit tests;
- route capability unit tests;
- provider adapter tests for OpenAI and OpenRouter Responses forwarding;
- endpoint allowlist and pipeline-ordering tests;
- PostgreSQL-backed mocked official OpenAI Python client E2E coverage.

Broader hosted-tool, background, and streaming
stateful Responses support remains future work until these are present and
green:

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
