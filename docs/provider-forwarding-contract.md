# Provider Forwarding Contract

This document describes exactly how implemented `/v1/chat/completions` requests
are forwarded to upstream providers. It also records the planned forwarding
constraints for future Responses API work. It is intended for code reviewers and
operators verifying implementation claims. Legacy `/v1/completions` is not
implemented in the current gateway.

## Provider Adapters

| Provider | Adapter | Upstream API shape | Implemented endpoint |
| --- | --- | --- | --- |
| OpenAI | `OpenAIProviderAdapter` | OpenAI Chat Completions | `POST /chat/completions` |
| OpenRouter | `OpenRouterProviderAdapter` | OpenRouter OpenAI-compatible Chat Completions | `POST /chat/completions` |

Anthropic-family, Google, Meta, Mistral, Qwen, and other non-OpenAI model names are supported only when a route sends them to OpenRouter's OpenAI-compatible interface. There is no native Anthropic adapter in this implementation.

Provider config rows, model route rows, pricing rows, and FX rows are local
metadata used by the existing provider factory, route resolver, pricing, and FX
estimate paths. The implemented admin dashboard can manage provider config,
route, pricing, and FX metadata where described in the compatibility matrix, but
those dashboard workflows do not change the forwarding contract, provider
adapter semantics, route-resolution algorithm, pricing algorithm, or FX lookup
semantics described below. Provider config rows store environment variable names
only, never provider key values. Dashboard route import has a preview/dry-run
workflow plus confirmed create-only execution. Execution re-parses and
re-validates CSV/JSON/TSV metadata server-side, requires CSRF, explicit
confirmation, and an audit reason, writes only valid new local `model_routes`,
and does not call providers. Confirmed imports can affect future route
resolution through the existing route-resolution algorithm; they do not change
provider forwarding or adapter semantics. Dashboard FX import has the same
preview plus confirmed create-only execution shape for local FX metadata.
Preview does not write `fx_rates`; execution re-parses and re-validates
server-side, requires CSRF, explicit confirmation, and an audit reason, writes
only valid new local `fx_rates`, and does not call external FX APIs or
providers. Confirmed FX imports can affect future EUR conversion through the
existing FX lookup path; they do not change provider forwarding, adapter
semantics, or FX lookup semantics.

Route and pricing endpoint values are normalized to local `/v1` paths for
runtime lookup:

| Operator value | Stored endpoint | Status |
| --- | --- | --- |
| `chat.completions` | `/v1/chat/completions` | Implemented |
| `/v1/chat/completions` | `/v1/chat/completions` | Implemented |
| `completions` | `/v1/completions` only after a future implementation adds normalization | Not implemented |
| `/v1/completions` | `/v1/completions` | Not implemented |

`slaif-gateway bootstrap openai-completions-catalog` seeds exact local
`/v1/chat/completions` routes and matching pricing rows from a curated in-repo
catalog plus an operator-controlled pricing CSV. The command does not call
OpenAI for model discovery, does not fetch pricing, and rejects legacy
`/v1/completions` route creation while that endpoint is not implemented. Seeded
Chat Completions routes include explicit `capabilities.chat_completions`
metadata for the currently supported request surface. Hosted search/tools,
image/file/audio inputs, custom tools, non-default service tiers, and multiple
choices are not enabled by that metadata.

`slaif-gateway provider-catalog propose ...` is separate from bootstrap and
from runtime forwarding. It can fetch official provider metadata to prepare
proposal TSV/JSON/Markdown artifacts, but it does not execute imports, does not
mutate local route/pricing rows directly, and does not change provider
forwarding until an operator later completes the existing import
preview/confirmation workflow.

## OpenAI Upstream Forwarding

| Area | Contract |
| --- | --- |
| Base URL | Route provider config `base_url` when configured; otherwise `https://api.openai.com/v1` |
| Upstream endpoint | `POST /chat/completions` |
| Provider auth | `Authorization: Bearer <OPENAI_UPSTREAM_API_KEY>` or route-configured `api_key_env_var` value |
| Client auth | Client `Authorization` is never forwarded |
| Non-streaming Accept | `application/json` |
| Streaming Accept | `text/event-stream` |
| Content-Type | `application/json` |
| Body reconstruction | Provider JSON is rebuilt from accepted Chat Completions fields after request policy, caps, capability checks, and gateway mutations; unknown top-level fields fail closed before forwarding |
| Body mutation | `model` is replaced with the resolved `upstream_model`; default output token control may be injected; streaming forces usage options |
| Successful non-streaming response | Provider JSON body is returned to the client after accounting finalization succeeds |
| Successful streaming response | Provider SSE events are forwarded for accepted fields, including text deltas, local function `tool_calls` deltas, `finish_reason="tool_calls"`, logprobs chunks, and structured-output-compatible chunks. Chat Completions streaming live-burn monitoring may interrupt the stream before provider completion when the per-key estimated cost/token cutoff is crossed. `[DONE]` is sent only after final accounting succeeds |
| Usage/accounting | Provider `usage` is parsed; local pricing and FX data compute actual EUR cost with cached/reasoning token handling where provider usage exposes it. Successful finalized requests record safe cost-source/confidence and reservation-overrun metadata and also persist advisory usage-profile metadata |
| Provider errors | Client receives a safe OpenAI-shaped error; raw provider body is not returned or stored; sanitized diagnostics may be stored. Streaming provider error events are converted to safe OpenAI-shaped SSE error events after reservation release |

`OPENAI_API_KEY` is reserved for client OpenAI-compatible configuration and is
never used as the gateway's upstream OpenAI provider secret. In production,
`OPENAI_UPSTREAM_API_KEY` must be configured for the enabled built-in OpenAI
provider, and route/provider config overrides must reference env var names only.

## OpenRouter Upstream Forwarding

| Area | Contract |
| --- | --- |
| Base URL | Route provider config `base_url` when configured; otherwise `https://openrouter.ai/api/v1` |
| Upstream endpoint | `POST /chat/completions` |
| Provider auth | `Authorization: Bearer <OPENROUTER_API_KEY>` or route-configured `api_key_env_var` value |
| Client auth | Client `Authorization` is never forwarded |
| Non-streaming Accept | `application/json` |
| Streaming Accept | `text/event-stream` |
| Content-Type | `application/json` |
| Model routing | Routes may use OpenRouter namespaced models such as `openai/...`, `anthropic/...`, `google/...`, or aliases that resolve to those names |
| Body reconstruction | Provider JSON is rebuilt from accepted Chat Completions fields after request policy, caps, capability checks, and gateway mutations; unknown top-level fields fail closed before forwarding |
| Body mutation | `model` is replaced with the resolved `upstream_model`; default output token control may be injected; streaming forces usage options |
| Successful non-streaming response | Provider JSON body is returned to the client after accounting finalization succeeds |
| Successful streaming response | Provider SSE events are forwarded for accepted fields, including text deltas, local function `tool_calls` deltas, `finish_reason="tool_calls"`, logprobs chunks, and structured-output-compatible chunks. Chat Completions streaming live-burn monitoring may interrupt the stream before provider completion when the per-key estimated cost/token cutoff is crossed. `[DONE]` is sent only after final accounting succeeds |
| Usage/accounting | Token usage is parsed; valid non-negative OpenRouter `usage.cost` or `usage.cost_usd` with supported currency is preferred for actual finalization while SLAIF-calculated cost remains comparison metadata. Invalid provider-reported cost falls back to SLAIF calculation. Successful finalized requests record safe cost-source/confidence and reservation-overrun metadata and also persist advisory usage-profile metadata |
| Provider errors | OpenRouter JSON and streaming error events produce safe diagnostics; raw provider bodies are not returned or stored. Streaming provider error events are converted to safe OpenAI-shaped SSE error events after reservation release |

In production, `OPENROUTER_API_KEY` must be configured for the enabled built-in
OpenRouter provider. DB-backed `provider_configs.api_key_env_var` values are env
var names only; readiness may report missing env var names but never secret
values.

Known limitations:

- The gateway does not fetch live OpenRouter billing or pricing.
- Native provider-specific APIs behind OpenRouter are not exposed.
- Provider-specific request fields are forwarded only after the Chat Completions
  field registry explicitly classifies them as supported; provider-specific
  headers are not generally forwarded.

## Responses Forwarding

Current Chat Completions forwarding remains unchanged. `POST /v1/responses` has
a limited text-output forwarding path, including stateless create and
non-streaming stored create when explicitly enabled.
`POST /v1/responses/input_tokens` has a separate provider-reported count
forwarding path for the same local input subset. `GET` and
`DELETE /v1/responses/{response_id}` are control-plane proxy calls after local
ownership checks. `POST /v1/conversations`, `POST`/`GET`/`DELETE
/v1/conversations/{conversation_id}`, plus
`POST`/`GET`/`DELETE /v1/conversations/{conversation_id}/items` are
control-plane proxy calls that use only safe provider conversation reference
metadata for ownership/routing; `POST /v1/responses` may forward a conversation
ID only after that ID resolves to an active local reference owned by the
authenticated gateway key and compatible with the resolved provider.

Responses forwarding follows the same provider-secret boundary:

- client `Authorization` is never forwarded upstream;
- provider authorization is substituted server-side from configured provider
  secrets or provider config env-var names;
- provider key values are never accepted from dashboard forms, request bodies,
  client headers, or import files;
- diagnostics are bounded and sanitized.

Provider-bound request bodies are not raw client JSON passthrough. For both
implemented provider paths, SLAIF first parses the OpenAI-compatible request,
validates the endpoint-specific field registry and caps, checks route/model
capability metadata, applies gateway mutations such as resolved model
substitution and output-token defaults, then constructs a fresh upstream JSON
object from an explicit allowlist of supported fields. If a future policy
result contains an unapproved top-level field, upstream body construction fails
closed instead of removing a few known-denied fields and forwarding the rest.
The approved construction path is an endpoint-specific normalized upstream
request contract followed by the canonical upstream payload builder; provider
adapters receive only the rebuilt `ProviderRequest.body`, never the raw client
request mapping.

Some nested payloads are intentionally opaque only inside documented supported
containers, such as local function-tool schemas, local custom-tool grammar
definitions, `response_format` schemas, bounded `metadata`, image URLs or
base64 image data, inline file `file_data`, and audio input/output fields where
the current Chat Completions policy enables them. The gateway still understands
the field path, type, size/count caps, capability requirement, redaction
boundary, and accounting policy for each such container. These opaque values
are inserted into a reconstructed parent object; the original client request
dictionary is not forwarded as-is.

Responses-specific rules for the current foundation:

- text output is supported for stateless create and for non-streaming
  `store=true` when the route explicitly enables stored Responses;
- `input` may be a string or a bounded message/input item array.
  Supported arrays are reconstructed from message roles plus string content or
  `input_text` content parts; string-only `function_call_output` items are
  reconstructed as ordinary stateless input for local function-tool follow-up
  requests, and string-only `custom_tool_call_output` items are reconstructed
  as ordinary stateless input for caller-managed custom-tool follow-up
  requests. Function-call/custom-tool-call items, reasoning/stateful items,
  hosted-tool items, `input_image.file_id`, `input_file.file_id`, and audio
  parts are rejected before provider forwarding;
- user-message `input_image` content parts are reconstructed only from
  `type`, `image_url`, and optional `detail` when route/model metadata
  explicitly enables `capabilities.responses.image_input=true`. Supported
  sources are fully-qualified `http`/`https` URLs without embedded credentials
  or fragments and configured base64 image data URLs. SLAIF does not fetch,
  decode, rewrite, store, or log image URLs/data URLs, and image bytes are used
  only for conservative admission estimates;
- user-message `input_file` content parts are reconstructed only from
  `type`, HTTPS `file_url`, or safe `filename` plus configured base64
  `file_data` data URL when route/model metadata explicitly enables
  `capabilities.responses.file_input=true`. SLAIF does not fetch file URLs,
  upload provider files, parse, OCR, index, extract text from, store, or log
  file URLs, filenames, data URLs, or base64 payloads. File IDs, file search,
  retrieval tools, and `/v1/files` lifecycle remain unsupported;
- local Responses function tools are reconstructed only from
  `tools[].type=function`, `name`, optional `description`, `parameters`, and
  optional `strict` after count/name/description/schema caps. Named
  `tool_choice` is reconstructed only when it references a declared local
  function. Function-tool schemas are opaque only under `tools[].parameters`;
  the gateway does not execute functions and does not forward hosted tool
  authority markers;
- local Responses custom tools are reconstructed only from
  `tools[].type=custom`, `name`, optional `description`, and optional `format`
  after count/name/description/grammar caps. Omitted custom format remains
  omitted. Explicit format is limited to text or grammar with `lark`/`regex`.
  Named custom `tool_choice` is reconstructed only when it references a
  declared local custom tool. The gateway does not execute custom tools, store
  generated custom-tool input, or forward hosted tool authority markers;
- non-streaming JSON and typed SSE streaming are supported when route/model
  metadata explicitly enables Responses streaming;
- non-streaming `text.format` JSON object mode and JSON schema structured
  output are forwarded only when route/model metadata explicitly enables
  `capabilities.responses.json_mode=true` or
  `capabilities.responses.structured_outputs=true`;
- `store=false` is injected when omitted;
- explicit `store=true` is forwarded only for non-streaming create after
  `capabilities.responses.stored_responses=true` is verified. After a
  successful provider response with an ID, SLAIF persists only safe response
  reference metadata needed for ownership and future provider routing;
- non-streaming `previous_response_id` is forwarded only after the ID resolves
  to an active local response reference owned by the authenticated gateway key,
  the route advertises `capabilities.responses.previous_response_id=true`, and
  provider/route metadata is compatible. Unknown, non-owned, deleted,
  provider-mismatched, or route-incompatible IDs are not proxied upstream;
- non-streaming `conversation` is forwarded only after the ID resolves to an
  active local conversation reference owned by the authenticated gateway key,
  the route advertises `capabilities.responses.conversations=true`, and
  provider metadata is compatible. Unknown, non-owned, deleted, or
  provider-mismatched conversation IDs are not proxied upstream. Conversation
  create/update/retrieve/delete provider requests are built from
  endpoint-specific normalized data and the stored provider conversation ID,
  never raw unchecked client IDs. Conversation update accepts metadata only,
  validates it conservatively, and does not store or log metadata values
  locally;
- `max_output_tokens` is defaulted or capped before forwarding;
- `/v1/responses/input_tokens` is routed and forwarded separately. Its
  canonical upstream body may include `input`, `instructions`, `text`, local
  `tools`, `tool_choice`, `parallel_tool_calls`, and `truncation`, but not
  create-only fields such as `stream`, `store`, or `max_output_tokens`. SLAIF
  forwards the provider's official `response.input_tokens` shape only after
  validating the object and non-negative integer count. It does not create a
  Response or reserve/finalize generation quota;
- `GET` and `DELETE /v1/responses/{response_id}` are built from the locally
  owned response reference, provider route metadata, and provider adapter path
  construction. Client-supplied response IDs are used only for local lookup; no
  retrieve/delete request is proxied when the reference is missing, non-owned,
  or locally deleted. These control calls do not forward a raw request body and
  do not create normal generation usage ledger rows;
- `GET /v1/responses/{response_id}/input_items` follows the same ownership
  boundary and additionally requires `capabilities.responses.list_input_items=true`
  on the stored route. The provider request uses the owned provider response ID
  plus only validated `after`, `limit`, `order`, and conservative `include`
  query parameters; SLAIF does not store, inspect, or log returned input-item
  content and does not create a normal generation usage ledger row;
- `POST /v1/responses/compact` is routed and forwarded separately through
  explicit `/v1/responses/compact` routes. Its canonical upstream body may
  include only `model`, required bounded text-focused `input`, and optional
  `instructions`. The provider request is rebuilt from normalized compact
  fields, not raw client bodies. Compact rejects streaming, storage/background
  state, `previous_response_id`, tools, hosted-tool markers, media/file/audio
  input, file IDs, and unknown fields in this first slice. SLAIF accounts
  compact as a model operation using endpoint-specific pricing, conservative
  admission reservation, and provider usage finalization, but does not store or
  log compact input, output, encrypted compaction content, or raw bodies;
- streaming preserves Responses event types such as `response.created`,
  `response.output_text.delta`, `response.completed`, and safe `error` events;
  it is not converted into Chat Completions chunks;
- streaming finalization uses provider usage from the completed response event,
  holds `response.completed` until finalization succeeds, and does not forward
  any upstream `data: [DONE]` marker as success before that finalization;
  missing final usage is not finalized as zero cost;
- structured `stream=true` requests are rejected in this slice; JSON schemas are
  accepted only as bounded opaque payloads inside `text.format`, counted for
  input estimation, and not stored or logged;
- unsupported tool/media fields are rejected and are not blind passthrough;
- future supported tool types must be explicitly allowlisted by key or key
  template;
- MCP/connectors are excluded;
- `background`, streaming conversation, and
  streaming `previous_response_id` are rejected before provider forwarding;
- response cancel and response listing require explicit provider response
  ownership mapping before they can be implemented;
- provider response IDs and tool diagnostics must be treated as metadata and
  sanitized before storage or display.

OpenRouter's Responses API is beta and stateless. OpenAI's Responses API exposes
stateful/background/storage and hosted-tool surfaces. SLAIF fails closed on
those differences until the policy, pricing, ownership, and accounting contracts
are implemented and tested. OpenRouter Responses is available only through
explicit `/v1/responses` route metadata; model allowlists alone do not enable it.

## Capability Policy Boundary

SLAIF treats endpoint, model, provider, and capability permissions as separate
checks. Current `/v1/chat/completions` forwarding allows local/client-side
function tools, legacy `functions` / `function_call`, `response_format`, JSON
mode, and normal streaming. SLAIF does not execute or police downstream
application code that handles a local function call.

Hosted/provider-side tools are denied by default for Chat Completions because no
persisted hosted-tool policy exists. Requests are rejected before Redis rate
limiting, route resolution, pricing lookup, PostgreSQL quota reservation, or
provider forwarding when they include `web_search_options`, hosted tool types
such as `web_search`, `web_search_preview`, `file_search`, `code_interpreter`,
`computer` / `computer_use`, `image_generation`, or `tool_search`,
MCP/connectors markers such as `server_url`, `connector_id`, provider-side
`authorization`, or `require_approval`, unknown tool types,
`background=true`, `external_web_access`, or search-specific Chat Completions
models such as `gpt-5-search-api`.

The Chat Completions field registry is also fail-closed. Standard keys and
trusted calibration keys reject unknown top-level Chat Completions fields with
`unknown_chat_completion_field`. Current forwarding supports text message
content, route-enabled image URL content parts, local function tools,
route-enabled non-streaming local custom tools, route-enabled bounded multiple choices, route-enabled non-streaming audio output, legacy function fields,
`response_format`, `prediction`, metadata within the gateway size cap,
omitted/`auto` `service_tier`, text-only `modalities`, and route-enabled
`modalities=["text","audio"]` with top-level `audio`. It rejects
non-default `service_tier`, unsupported audio/file/video content, alternate image part names, provider-side state
fields such as `store=true`, `previous_response_id`, and `conversation`, and
other unclassified feature-bearing fields before any provider request is built.

Supported Chat Completions fields are also bounded by explicit scalar and size
validation before any provider body is constructed. The gateway validates
temperature/top-p/penalty/logprob/logit-bias ranges, message/text/image-part
counts, remote image URL and image data URL byte caps, image detail values,
local function-tool counts and schema sizes, response-format schema size,
metadata key/count/byte limits, stop sequence limits, `prediction` size,
`stream_options` size, and bounded `n`. Rejection errors do not include raw
messages, image URLs, base64 image/audio payloads, audio transcripts, metadata values, schemas, tool
payloads, or request bodies.

Route/model capability metadata is checked after route resolution and before
Redis rate limiting, pricing lookup, quota reservation, or provider forwarding.
The key model allowlist is not sufficient by itself: the resolved route must
also allow the request's Chat Completions shape. Current capability flags cover
text chat, streaming, local function tools, local custom tools, legacy functions, JSON mode,
structured outputs, logprobs, reasoning-usage signals, cached-input usage
signals, hosted tool families, image inputs, broader multimodal/audio/file
inputs, audio-input flags, non-default service tiers, and multiple choices. New Chat Completions routes created by the
route service receive explicit conservative metadata. Existing legacy routes
without a `chat_completions` block use a compatibility fallback for the
previously supported surface, while malformed or unknown `chat_completions`
capability flags fail closed.

## Header Contract

| Header | Client to gateway | Gateway to provider | Gateway to client | Behavior |
| --- | --- | --- | --- | --- |
| `Authorization` | Required as gateway Bearer token | Replaced with provider Bearer token | Not echoed | Client gateway key never leaves the gateway |
| `Content-Type` | Accepted for JSON requests | Sent as `application/json` | Provider response dependent | Provider request bodies are JSON |
| `Accept` | May be sent by client | Forced to `application/json` or `text/event-stream` based on request mode | Provider response dependent | Streaming requests use SSE Accept upstream |
| `X-Request-ID` | Safe incoming value may be accepted by middleware | Forwarded as the gateway request ID | Response includes gateway request ID | Used for tracing without exposing secrets |
| `Cookie` | Not used for `/v1` auth | Never forwarded | Not forwarded from provider except allowlisted safe headers | Blocks browser/session leakage |
| `Set-Cookie` | Not applicable | Not sent | Not exposed from provider | Blocks provider/admin session leakage |
| CSRF/session/admin headers | Not used for `/v1` auth | Never forwarded | Not exposed | Internal/admin headers stay internal |
| Provider request ID headers | Not sent by client | Not generated except gateway `X-Request-ID` | Safe provider request IDs may be retained in metadata/headers | Useful for diagnostics when provider returns them |

Outbound provider header construction uses a small allowlist. Header names containing authorization, cookie, CSRF, session, password, token, secret, admin, gateway, API key, or set-cookie fragments are blocked.

## Body Mutation Contract

| Field | Behavior | Reason |
| --- | --- | --- |
| `model` | Mutated upstream | Replaced with route `upstream_model` for aliases and provider-specific naming |
| `messages` | Preserved when valid and within configured caps | Required Chat Completions input; used only for validation and token estimation, not stored. User-message `image_url` parts are preserved only with explicit `chat_image_inputs=true` route capability; user-message inline `file` parts are preserved only with explicit `chat_file_inputs=true` route capability; user-message `input_audio` parts are preserved only with explicit `chat_audio_inputs=true` route capability |
| `max_tokens` | Preserved when valid | OpenAI Chat Completions output control |
| `max_completion_tokens` | Preserved when valid or injected if no output-token field exists | Bounded output is required for quota reservation |
| `stream` | Preserved; streaming path selected only when `true` | Controls JSON vs SSE response |
| `stream_options` | Preserved, but `include_usage` forced to `true` for streaming | Required for reliable streaming accounting |
| `n` | Preserved when omitted, `1`, or route-enabled and within `CHAT_MAX_CHOICES_PER_REQUEST` | Output-token controls remain per choice; reservation and estimated output cost multiply possible output by `n`, while final provider usage/cost is used once |
| `tools` / `tool_choice` | Preserved when accepted and within configured local-tool caps; serialized object/list payloads are included in input/cost pre-reservation | Local `function` tools are allowed as client-side behavior. Non-streaming local `custom` tools are allowed only when the resolved route explicitly enables `chat_custom_tools`; SLAIF does not execute them or inspect their downstream meaning. Hosted/provider-side tools, MCP/connectors, web search tools, unknown tool types, and tool choices that force denied hosted tools are rejected before forwarding |
| `functions` / `function_call` | Preserved when accepted and within equivalent caps; serialized object/list payloads are included in input/cost pre-reservation | Legacy OpenAI-compatible function fields may affect provider context size |
| `response_format` | Preserved when accepted; bounded JSON schemas are included in input/cost pre-reservation | Ordinary OpenAI Chat Completions field that can affect provider context size |
| `metadata` | Preserved to provider only when it is a JSON object within configured key/count/byte caps; not stored wholesale in ledger | Ordinary OpenAI Chat Completions field with explicit size/shape policy |
| `user` | Preserved within configured byte cap | Ordinary OpenAI Chat Completions field |
| `temperature` / `top_p` / penalties / logprob controls / `logit_bias` | Preserved when type and range validation passes | Ordinary OpenAI Chat Completions scalar controls |
| `prediction` | Preserved when accepted as a bounded object; object payload is included in input/cost pre-reservation | Static-output hints can affect provider context size |
| `service_tier` | Omitted or `auto` is allowed; other values are rejected | Local pricing is not service-tier aware |
| `image_url` content parts | Preserved when accepted and within image count/byte/detail caps | Image input is request input, not a hosted tool or image-generation tool. SLAIF does not fetch remote URLs, decode/rewrite data URLs, store/log image URLs or base64 payloads, or infer final image billing from bytes |
| `file` content parts | Preserved when accepted and within file count/byte/type caps | Inline file input is request input, not hosted file search, retrieval, code interpreter, or `/v1/files`. SLAIF forwards only validated `filename` plus inline `file_data`; file IDs and file URLs are rejected. SLAIF does not fetch, upload, decode/rewrite, store/log file payloads, filenames, file IDs, or file URLs, or infer final file billing from bytes |
| `input_audio` content parts | Preserved when accepted and within audio count/byte/format caps | Audio input is request input, not audio output, `/v1/audio/*`, Realtime, or a hosted tool. SLAIF forwards only validated raw base64 `data` with `format` `wav` or `mp3`; audio URLs and audio data URLs are rejected. SLAIF does not fetch, transcribe, decode/rewrite, store/log audio payloads or decoded bytes, or infer final audio billing from bytes or duration |
| `modalities` / `audio` / unsupported non-text content parts | Text-only modality is allowed. Non-streaming audio output is forwarded only with explicit `chat_audio_outputs=true`, valid `audio` config, and configured audio-output pricing metadata. Supported output formats are `wav`, `aac`, `mp3`, `flac`, `opus`, and `pcm16` with built-in voice strings only. Streaming audio output, `n > 1` with audio output, custom voices, previous-audio references, video fields, alternate image/file/audio part names, file IDs, file URLs, and audio URLs are rejected | SLAIF forwards validated audio-output request fields and preserves non-streaming provider `message.audio` responses without storing/logging generated audio data or transcripts. Audio-output cost is finalized from provider usage/cost; aggregate provider usage remains authoritative, optional audio-token detail is recorded only as safe usage metadata, and bytes, transcript length, format, voice, and duration are not exact billing units |
| Unknown top-level fields | Rejected before forwarding with `unknown_chat_completion_field` | The gateway must not silently pass future feature-bearing fields through endpoint/model authorization alone |
| Gateway-internal data | Rejected/not present in provider body | Routing, quota, rate-limit, and accounting state must not be sent upstream |

`n > 1` is a bounded forwarding feature, not a new billing category. It requires
`chat_multiple_choices=true` on the resolved route. Input is estimated once,
possible output is reserved as `effective_max_output_tokens_per_choice * n`,
and final provider usage or OpenRouter provider-reported cost is not multiplied
again by `n`.

Chat Completions image input to text output is forwarded only when route
metadata explicitly enables `chat_image_inputs`. Remote URLs and image data
URLs are bounded and forwarded as client-provided `image_url.url` values; SLAIF
does not fetch, decode, rewrite, store, or log them.

Chat Completions inline file input to text output is forwarded only when route
metadata explicitly enables `chat_file_inputs`. SLAIF forwards documented
`file` content parts with `filename` and inline `file_data` after byte,
filename, extension, MIME/data-URL, and base64 validation. Raw base64 is
accepted by default; data URLs are opt-in with MIME caps. File IDs and file
URLs remain unsupported, and SLAIF does not fetch URLs, call `/v1/files`, upload
files upstream, rewrite payloads, store/log file data, filenames, file IDs, or
file URLs, or infer exact final file cost from bytes.

Chat Completions audio input to text output is forwarded only when route
metadata explicitly enables `chat_audio_inputs`. SLAIF forwards documented
`input_audio` content parts with raw base64 `data` and `format` `wav` or `mp3`
after byte, count, format, and base64 validation. Audio URLs and audio data
URLs remain unsupported, and SLAIF does not fetch audio URLs, transcribe
locally, rewrite payloads, store/log audio data or decoded bytes, or infer exact
final audio cost from bytes or duration.

Chat Completions non-streaming audio output is forwarded only when route
metadata explicitly enables `chat_audio_outputs` and the active pricing rule
sets `pricing_metadata.audio_output_price_per_1m`. SLAIF forwards documented
`modalities: ["text", "audio"]` and top-level `audio` config with built-in
voices and allowlisted formats (`wav`, `aac`, `mp3`, `flac`, `opus`,
`pcm16`), preserves provider `choices[].message.audio`
responses, and does not transcode, decode, rewrite, store, or log generated
audio data or transcripts. Streaming audio output, `n > 1` with audio output,
custom voices, and assistant previous-audio references remain unsupported.

Image generation and broader multimodal media-response combinations remain
unsupported and must be explicit future work because response media bytes and
modality-specific usage fields create separate privacy, request-size,
estimation, pricing, and accounting requirements.

The gateway does not intentionally store prompt, completion, full request body, full response body, tool payload, or streamed chunk content in `usage_ledger`.

Large serialized non-message provider-forwarded fields can be rejected by the
request policy before provider forwarding. The estimator is deterministic,
dependency-free, and conservative: it counts message input plus canonical JSON
byte-size upper bounds for forwarded non-message object/list fields. It may
over-reserve, but it must not under-reserve known large tool/function/schema
surfaces. Actual provider usage still finalizes accounting when available.

## Accounting Contract

For `POST /v1/chat/completions`:

1. Authentication and endpoint policy run before provider work.
2. Request policy validates shape, estimates input tokens including serialized
   non-message provider-forwarded object/list fields, and bounds maximum output.
3. Redis operational rate limiting runs when enabled.
4. Route resolution selects provider and upstream model.
5. Pricing/FX lookup estimates maximum cost.
6. PostgreSQL hard quota reservation is committed before the provider call.
7. Provider forwarding happens after reservation. The provider call is not made while holding the quota row lock.
8. Successful provider responses are finalized using provider usage, even when
   actual tokens or cost exceed the admitted reservation.
9. Failed provider responses release the pending reservation and create a failed usage ledger row when a reservation exists.
10. Successful accounting increments used counters, clears reserved counters, finalizes the reservation, writes/finalizes a ledger row, and records token/cost metrics.

This is an admission-time budget check plus post-call spend accounting model,
not hard real-time spend interruption inside one upstream call. If finalization
puts the key above local token or cost limits, subsequent calls are blocked by
normal quota admission until limits are raised or usage is reset.

Chat Completions and the supported stateless text-output Responses streaming
live-burn monitoring are documented in
[`streaming-live-burn-margin.md`](streaming-live-burn-margin.md). They are
gateway-side, provisional stream interruption brakes for visible streamed text
only. They are not invoice-grade billing truth and do not replace PostgreSQL
reservation/finalization or provider final usage/cost.

Chat live-burn reporting is post-hoc operator visibility over safe usage
ledger metadata. It does not alter provider forwarding, streaming
finalization, Redis concurrency state, or provider-completed reconciliation.

### Streaming Accounting

Streaming has an extra finalization rule because content may already have reached the client:

- Supported provider chunks are counted and validated before forwarding.
- The forwarded chunk surface includes plain text deltas, local/client-side
  function `tool_calls` deltas, `finish_reason="tool_calls"`, provider
  `logprobs` data, and response-format-compatible JSON/text deltas when those
  request fields pass policy.
- Final provider usage is required for success.
- If usage is missing after token-bearing output reached the client, the
  request is finalized as estimated interrupted usage instead of full
  reservation release. If no token-bearing output was observed, the existing
  release/failure path may be used.
- If usage is present, the gateway writes a durable provider-completed record before final counter mutation.
- If finalization succeeds, that record is marked finalized and `[DONE]` is emitted.
- If finalization fails, the record is marked with `needs_reconciliation=true` and `recovery_state=provider_completed_finalization_failed`; `[DONE]` is not emitted.
- Operator reconciliation can later finalize these provider-completed rows using stored usage/cost metadata without calling providers.
- For Chat Completions only, per-key streaming live-burn monitoring estimates
  admission input plus visible generated `choices[].delta.content` and function
  tool-call name/argument deltas before forwarding chunks. If the estimated
  request cost or token burn crosses the configured cutoff, SLAIF stops the
  upstream stream when possible, emits a safe SSE error with code
  `streaming_live_burn_limit_exceeded`, suppresses normal `[DONE]`, and
  withholds the threshold-crossing chunk.
- For the supported stateless text-output Responses streaming subset, per-key
  live-burn monitoring estimates admission input plus visible generated
  `response.output_text.delta` text before forwarding typed SSE events. If the
  estimated request cost or token burn crosses the configured cutoff, SLAIF
  stops the upstream stream when possible, emits a safe typed Responses error
  event with code `streaming_live_burn_limit_exceeded`, suppresses normal
  `response.completed` / `[DONE]` success markers, and withholds the
  threshold-crossing delta.
- If provider final usage is unavailable because SLAIF intentionally stopped a
  Chat stream for live-burn, the request is finalized as estimated interrupted
  accounting with safe metadata. It is not released as normal zero-cost success.

Responses streaming uses typed SSE events rather than Chat Completions chunk
objects. For Responses, the gateway holds `response.completed` until
usage-backed finalization succeeds; if an upstream provider also sends
`data: [DONE]`, it is held behind the completed event and is not emitted on
missing-usage or finalization-failure paths.

Streaming does not expand request policy. Hosted/provider-side tools, custom
tools, web search, MCP/connectors, external web access, file/audio content,
non-default `service_tier`, background/provider-state lifecycle
fields, and unknown top-level fields remain rejected before provider
forwarding. Streaming `n > 1` is supported when route metadata explicitly
enables multiple choices; SSE chunks, choice indexes, finish reasons, the final
usage chunk, and `[DONE]` are preserved without buffering the full stream.

Live-burn interruption remains gateway-side. Provider-bound request bodies and
headers must not receive live-burn counters, margins, internal quota state,
Redis keys, or gateway diagnostics, and the gateway must not store raw streamed
content while estimating live burn.

### Reconciliation

Manual quota reconciliation supports:

- Expired pending reservation repair for crash/stale cases.
- Provider-completed finalization-failure repair for streaming requests that already received final usage.

Provider-completed finalization failures are not treated as zero-cost provider failures. The repair path uses stored safe usage/cost metadata and does not call upstream providers.

## Safety Boundaries

- Provider API keys come from server settings or provider config environment variable names; they are not accepted from clients.
- Client gateway keys, provider keys, token hashes, cookies, sessions, and Authorization headers are not stored in ledger metadata.
- Raw provider response bodies are not returned to clients or stored.
- Provider diagnostics are bounded and sanitized.
- Normal tests mock upstream OpenAI/OpenRouter with RESPX and do not require real provider keys.
