# Responses Compatibility Contract

Status: limited foundation implemented on current `main`.

Codex CLI wire compatibility is tracked separately in
[`codex-compatibility.md`](codex-compatibility.md). The pinned Codex CLI 0.147.0
`gpt-5.6-sol` API-key Responses profile has **PARTIAL STREAMING CLIENT-TOOL
ROUND-TRIP SUPPORT AND IS NOT CODEX-COMPATIBLE**. The bounded envelope, exact
Responses-lite client-tool declaration taxonomy, strict tool-event stream, and
one linked replay are implemented behind three independent key/route
capabilities. The capture itself does not authorize Codex tools or broader
provider/client authority.

This document defines the RC2-beta support boundary for Responses API work.
It does not define feature-full RC2 by itself; standalone `/v1/audio/*` and
`POST /v1/embeddings` are implemented separately, while the bounded Realtime
client-secret foundation is implemented and the remaining Realtime
sub-surfaces are tracked separately in
[`rc2-feature-scope.md`](rc2-feature-scope.md).
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
- behind both `codex_request_envelope` gates only: exact
  `include=["reasoning.encrypted_content"]`, boolean `parallel_tool_calls`,
  bounded opaque `prompt_cache_key`, bounded `reasoning.effort` plus optional
  `reasoning.context="all_turns"`, `text.verbosity` as `low|medium|high`, and a
  bounded conservative `id` on otherwise-supported message items

The Codex request-envelope gates are independent and default-deny. The
authenticated key's sanitized `responses_policy.allowed_capabilities` must
explicitly include `codex_request_envelope`, and the resolved route must set
`capabilities.responses.codex_request_envelope=true`. Missing or malformed key
policy fails before route/database work; a missing/false route flag fails before
Redis, pricing, quota, or provider work. Neither endpoint/model permission nor
Codex-like headers grants this capability.

Bounded `client_metadata` presence also triggers both gates. Only the pinned
0.147.0 installation/session/thread/window/turn key vocabulary is accepted and
all values must be capped strings. The gateway does not parse embedded
`x-codex-turn-metadata` JSON. After validation, it drops the complete object;
client metadata is never forwarded, persisted, logged, audited, metered,
hashed, exported, or echoed. Prompt-cache values and message IDs are forwarded
only as validated opaque provider input and are never persisted, logged,
audited, exported, echoed, or used as identity/state authority.

If `store` is omitted, SLAIF injects `store=false` before provider forwarding so
the gateway remains stateless even when an upstream default would store
responses. Explicit `store=true` requires `stream=false` and
`capabilities.responses.stored_responses=true`; it persists only safe provider
response reference metadata after a successful provider create response with an
ID. If `max_output_tokens` is omitted, ordinary Responses injects the existing
1,024 default output cap. A request with all four existing Codex gates uses its
strict route numeric default instead (32,768 for the qualification profile),
bounded by route/operator maximums and the route context window. The
1,050,000/128,000 qualification limits and pricing multipliers are configured
model data, not universal hardcoded facts. Streaming uses typed Responses SSE events such as
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

An independently gated Codex V1 compact request requires all four existing
Codex key/route capabilities plus default-off `codex_compaction`, strict
`codex_limits`, and the ordinary endpoint/model/provider/pricing policy. It may
carry only the exact pinned model, history, instructions, tools,
`parallel_tool_calls`, reasoning, `prompt_cache_key`, and text controls. It
rejects `stream`, `store`, `include`, `tool_choice`, background, hosted/MCP
authority, V2 `compaction_trigger`, provider-state IDs, media, and unknown
fields. Prior reasoning/tool/compaction history must pass same-key HMAC lookup
before side effects. A different compact route row requires explicit same-
provider/same-upstream-model compatible-route metadata.

With all five Codex key capabilities, pinned create/compact history may also
contain exact `internal_chat_message_metadata_passthrough` on message (including
omitted `type`), reasoning, function/custom call and output, or compaction
items. The value must be null or a canonical JSON object no larger than 32,768
bytes. The gateway copies the item, validates only that type/size boundary, and
drops the field before ordinary item validation, canonicalization, metering,
replay/HMAC extraction, or forwarding. It contributes zero input tokens and
cannot reach provider bodies, persistence, logs, audits, metrics, exports,
errors, or safe evidence. `additional_tools`, hosted or unknown item types,
ordinary requests, missing-gate requests, and other endpoints continue to
reject the field rather than dropping or forwarding it.

Fully gated Codex client-tool history may preserve optional bounded `id` on
`function_call_output` and `custom_tool_call_output`. A present value must pass
the existing 128-character ASCII-safe Codex item-ID validator, is canonicalized
unchanged, contributes its complete canonical bytes to input-token/cost
estimation, and must be unique across every request history item ID. It is not
a separate replay/HMAC reference: the output remains authorized only by the
immediately preceding matching HMAC-owned call and `call_id`. Absent IDs retain
the prior canonical shape. Ordinary outputs, malformed or duplicate IDs,
unknown fields, orphan/reordered/cross-type pairs, and linkage mismatches remain
denied. Raw output IDs are transient provider input and never enter safe
evidence or persistence.

The pinned V1 compact request does not carry `max_output_tokens`. SLAIF keeps
that field absent in the provider request while using the validated Codex route
maximum (128,000 for the qualification profile) as effective/requested output
exposure for context admission, quota reservation, pricing, and safe evidence.
This exception changes neither ordinary compact's configured default nor
ordinary Responses output-default behavior.

The Codex provider response must contain supported final usage and exactly one
opaque `compaction` item with a safe ID and non-empty capped encrypted content.
Its top level allows only required `output` and `usage` plus optional validated
`id`, `object`, and `created_at`; unknown fields, malformed metadata or usage,
extra output, and plaintext item fields are rejected.
After finalized PostgreSQL accounting, SLAIF stores only a versioned composite
HMAC over both opaque values plus safe ownership/routing/expiry metadata before
recording the normal compact success metric and returning success. HMAC
persistence failure remains charged but returns a safe 500-class error and no
normal success metric. Neither raw value is stored or inspected. Later gated create
or compact history must prove that composite HMAC. This is client-managed
opaque V1 history, not local content storage; V2, background, and hosted tools
remain unsupported.

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
Function-call and custom-tool-call items are accepted only for the exact gated
Codex replay described below. Exact opaque encrypted reasoning is accepted only
for that separately gated replay. Other call items, arbitrary reasoning/stateful
items, hosted-tool items, and audio content parts are rejected before Redis
rate limiting, pricing lookup, quota reservation, or provider forwarding.
`input_image.file_id` remains
unsupported until `/v1/files` ownership and provider-file lifecycle are
implemented. String-only
`function_call_output` items are supported as ordinary stateless input for local
function-tool follow-up requests; image/file outputs in tool-result items remain
rejected. Input item arrays use the same Responses text/stateless route
capability as string input; image input additionally requires
`capabilities.responses.image_input=true`, and file input additionally requires
`capabilities.responses.file_input=true`. They compose with plain text streaming,
non-streaming structured `text.format`, and local function tools; structured
streaming and ordinary top-level function-tool streaming remain rejected. The
separately gated Codex declaration/event/replay slice is described below.

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

The bounded Codex envelope composes with this existing route policy but does
not broaden it. A separately gated `additional_tools` input slice accepts only
the pinned `functions` namespace (`exec`, `wait`, `request_user_input`) and
`collaboration` namespace (`followup_task`, `interrupt_agent`, `list_agents`,
`send_message`, `spawn_agent`, `wait_agent`). It requires both
`codex_request_envelope` and `codex_client_tools` on the key and route; neither
implies the other or ordinary top-level function/custom-tool permission.
Namespace/tool placement and types are exact, schemas/grammar/descriptions are
bounded, `exec` must use an allowlisted grammar, and `tool_choice` is limited to
`none`, `auto`, or `required`. Hosted/MCP/provider authority, arbitrary or
nested namespaces, gateway execution, and background/storage expansion still
fail closed. Child function/custom descriptions use a fixed 20,000-byte per-
description qualification cap only in this exact gated taxonomy, with 32,768
bytes total across namespace and child descriptions. Namespace and ordinary
top-level function/custom descriptions keep their 4,096-byte limits. Approved
`functions.request_user_input` may use singular schema property `header` only
at `parameters.properties.questions.items.properties.header`, where it is a
short UI label. Recursive scanning remains active below and beside that exact
property; plural/alternate header fields, other paths/tools, and every provider
authority marker still fail closed. Ordinary tool behavior is unchanged.
All approved envelope, message-ID, declaration, description, schema, grammar,
and choice
bytes increase the conservative admission estimate; safe estimation evidence
contains only approved categories and aggregate bytes/tokens, never private
values. Dropped client metadata is size-capped but is not provider-billed input.

Streaming call events and replay require a third capability,
`codex_streaming_tool_events`, on both the key and route in addition to the two
capabilities above. The key denial occurs before route/database work and route
denial before Redis, pricing, quota, or provider work. A request-scoped
validator accepts only the documented created/in-progress, output-item
added/done, function-argument delta, custom-input delta, reasoning
summary-part/text, reasoning-text, output-text, and completed event families.
It enforces bounded IDs, indexes, deltas, cumulative values, sequence, exact
request declarations, and call/item linkage frame by frame. Unknown events,
orphan/duplicate/mismatched calls, hosted authority, and provider failure/error
terminals become a safe gateway error rather than unchecked passthrough.

A next stateless request may replay only the exact validated declared function
or `functions.exec` custom call with one immediately following matching output.
Function output is a bounded string. For the pinned Code Mode `functions.exec`
path, custom output may also be its bounded exact list of `input_text` parts.
Orphans, reorderings, duplicates, unknown names/namespaces/types, mismatched
call IDs, unapproved authority, and oversize arguments/results are rejected.
Reconstructed items are deep-copied and all canonical bytes are counted as
input.

Provider-encrypted reasoning output and replay additionally require the
independent default-off `codex_encrypted_reasoning_replay` capability on the
key and route together with `codex_request_envelope`. The exact reasoning
`response.output_item.done` shape requires a bounded ID, exact summary-text
array, and non-empty opaque `encrypted_content` under per-item and cumulative
caps. The replay request additionally permits only the pinned client's exact
`content=null`; the done event itself remains the exact four-field item.
Plaintext/non-empty `content`, wrong-event placement, unknown/status/authority
fields, and malformed or oversized values fail closed. The accepted upstream
frame remains unchanged in transit.

Fully validated reasoning and function/custom done items receive reusable
24-hour HMAC-only references after final provider usage and successful
PostgreSQL accounting. A replay request must resolve every item/call ID to the
same key before route work and then match provider, route, model, kind, and
approved tool identity before Redis/pricing/quota/provider work. Raw IDs,
digests, encrypted reasoning, summaries, arguments, and results never persist
or appear in logs/metrics/audit/errors. Cross-key, expired, unavailable HMAC
version, and compatibility mismatches deny safely. Client-managed replay cannot
combine with `previous_response_id`, stored Response state, or `conversation`.
Codex/the downstream client owns local tool execution; SLAIF does not execute
the call. The bounded V1 compact slice above does not establish full
CLI-through-production-provider compatibility.

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
- OpenAI's canonical Responses `web_search` shape is provider-contract-qualified
  only by Objective 016. It permits only `search_context_size` (`low`,
  `medium`, or `high`) and a positive top-level `max_tool_calls`, requires
  `store=false`, no background/previous-response/conversation/approval
  continuation, neutral absent/`auto` tool choice, and the exact fenced
  `provider_web_search` key/route decision. Preview aliases, filters, location,
  external-web controls, returned-token controls, arbitrary instructions,
  other hosted tools, MCP, and connectors remain rejected. Runtime forwarding
  remains denied pending Objective 017; if activated, published per-call fee
  and provider token usage use the full-balance fence and unknown-evidence hold.
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

The qualified web-search contract is content-free: no prompt, query, URL,
source, result, citation, tool content, OAuth token, or provider secret is
persisted, logged, returned in safe evidence, or reconstructed into a provider
body beyond the approved declaration and `max_tool_calls`.

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

For a successful gated Codex replay stream, finalized accounting is followed by
a same-key/source-ledger verification and HMAC-only reference commit while
`response.completed` remains held. Reference persistence failure emits a safe
typed error and suppresses normal completion while preserving the already
charged/finalized usage. Missing usage, malformed/provider-error events, and
disconnects never create usable references.

Streaming live-burn margin for Responses typed SSE is implemented for the
currently supported stateless text-output subset and the explicitly gated
Codex streaming client-tool event slice. The governance
milestone is [`streaming-live-burn-margin.md`](streaming-live-burn-margin.md).
SLAIF counts visible output-text, function-argument, custom-input,
reasoning-summary, and reasoning-text deltas and discards their content after
counting. Matching done events do not double count prior deltas; a bounded done
value is counted only when no matching delta was observed. SLAIF may stop the
upstream stream when estimated request cost or token burn crosses the cutoff,
and withholds the threshold-crossing event. Provider final usage remains
authoritative when it arrives before an abort. Missing usage, provider error,
or client disconnect after any counted output finalizes as estimated
interrupted usage rather than normal success. This feature does not enable
background mode, cancel, response listing, Responses audio, or stateful
streaming with `store=true`, `previous_response_id`, or `conversation`.

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

Objective 012 defines two external-tool quota modes. Objective 013 stores their
canonical key/template/route policy and audited operator configuration without
enabling forwarding. `strict_bounded` is current/default and denies
provider-hosted/external authority. Existing client-operated `function`,
`custom`, gated `namespace`, `local_shell`, and client-side `apply_patch`
workflows remain under their independent policies. `external_tool_fenced` is a
future standard-key opt-in requiring exact key/route capability and reviewed-
destination intersections, operator ceilings, finite positive request/token/EUR
limits, final-usage/final-cost evidence, and literal overrun acknowledgement.

The fenced promise is exact: one admitted provider-hosted external-tool request
may exceed the key's remaining token or cost quota before SLAIF regains control.
SLAIF will reject concurrent requests for that key while the request is
unresolved, finalize authoritative provider usage/cost when available, reject
following requests after exhaustion, and retain a blocking accounting hold
when final cost is missing, ambiguous, interrupted, or awaiting reconciliation.

Provider web/file search, code interpreter, hosted shell, image generation,
computer use, tool search, skills, remote MCP, connectors, and provider URL
fetch have separate canonical capability IDs. Unknown/malformed/mixed authority
fails closed. Client MCP/network behavior outside provider wire authority is a
client responsibility; SLAIF cannot claim to observe or block undeclared client
action. Provider background execution, stored/previous-response state, and
provider authentication remain distinct unsupported surfaces and are not
implicitly enabled. Objective 014 implements the fence and
full-remaining-balance reservation foundation on the locked key row. Objective
015 implements the manual accounting hold/reconciliation path; external
forwarding remains disabled. Objective 016 qualifies the selected OpenAI
web-search provider contract, and Objective 017 owns runtime integration. The
exact overrun and one-winner concurrency promise remains conditional on that
later activation. Current Responses
runtime remains deny-only for every provider-hosted/external tool.

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
- explicit per-key `codex_request_envelope` capability for the bounded non-tool
  envelope; no default or trusted-calibration discovery grant
- explicit per-key `codex_client_tools` and
  `codex_streaming_tool_events` capabilities for the pinned declaration and
  streaming round-trip slices; no default or trusted-calibration discovery
  grant

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
`list_input_items`, `compact`, `conversations`, `conversation_items`,
`codex_request_envelope`, `codex_client_tools`,
`codex_streaming_tool_events`, `codex_encrypted_reasoning_replay`,
`codex_compaction`), allowed local
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

The five Codex capabilities may appear in that capability list only when the
reviewed template snapshot explicitly includes each one. Template normalization
and calibration discovery never add them by default. The streaming capability
is rejected unless both prerequisite capabilities are also present.
Client-tool declarations require the first two capabilities on the created key
and route; streaming call/replay requires all three. Encrypted reasoning replay
requires its fourth capability plus the request envelope. Compaction requires
all four earlier gates plus its fifth independent capability. Copying any
capability does not enable hosted tools, storage, background, MCP, gateway
execution, or a Codex compatibility claim.

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

## Objective 017 hosted web-search boundary

The gateway supports one bounded hosted family: OpenAI Responses `web_search`
with the exact canonical declaration, `max_tool_calls`, `store=false`,
stateless execution, OpenAI routing, explicit per-key and per-route
`external_tool_fenced` policy, finite limits, and configured per-call pricing.
Admission occurs before Redis, PostgreSQL mutation, or provider forwarding.
PostgreSQL reserves the key's full remaining balance, permits one bounded
overrun, and clears the fence only after authoritative usage and call evidence
are finalized. Unknown outcomes keep the reservation in a durable hold for
manual reconciliation. Streaming holds terminal completion until the same
evidence and accounting boundary succeeds.

Client function/custom tools remain client-operated and independent; Codex
local tools cannot be combined with hosted tools in one request. OpenRouter,
remote MCP/connectors, URL fetch, domain/location/source controls, background
state, and every other hosted family remain denied.

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
# External-tool accounting hold boundary

Responses provider-hosted external-tool forwarding is not enabled by the
accounting hold foundation. Missing or ambiguous final cost remains held and
reserved for explicit operator reconciliation.
