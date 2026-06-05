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
| Body preservation | Registry-classified OpenAI Chat Completions fields are preserved when accepted; unknown top-level fields fail closed before forwarding |
| Body mutation | `model` is replaced with the resolved `upstream_model`; default output token control may be injected; streaming forces usage options |
| Successful non-streaming response | Provider JSON body is returned to the client after accounting finalization succeeds |
| Successful streaming response | Provider SSE events are forwarded for accepted fields, including text deltas, local function `tool_calls` deltas, `finish_reason="tool_calls"`, logprobs chunks, and structured-output-compatible chunks; `[DONE]` is sent only after final accounting succeeds |
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
| Body preservation | Registry-classified OpenAI-compatible Chat Completions fields are preserved when accepted; unknown top-level fields fail closed before forwarding |
| Body mutation | `model` is replaced with the resolved `upstream_model`; default output token control may be injected; streaming forces usage options |
| Successful non-streaming response | Provider JSON body is returned to the client after accounting finalization succeeds |
| Successful streaming response | Provider SSE events are forwarded for accepted fields, including text deltas, local function `tool_calls` deltas, `finish_reason="tool_calls"`, logprobs chunks, and structured-output-compatible chunks; `[DONE]` is sent only after final accounting succeeds |
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
a limited stateless text-only forwarding path.

Responses forwarding follows the same provider-secret boundary:

- client `Authorization` is never forwarded upstream;
- provider authorization is substituted server-side from configured provider
  secrets or provider config env-var names;
- provider key values are never accepted from dashboard forms, request bodies,
  client headers, or import files;
- diagnostics are bounded and sanitized.

Responses-specific rules for the current foundation:

- only non-streaming text input/text output is supported;
- `store=false` is injected when omitted;
- `max_output_tokens` is defaulted or capped before forwarding;
- tool fields are rejected and are not blind passthrough;
- future supported tool types must be explicitly allowlisted by key or key
  template;
- MCP/connectors are excluded;
- `background`, `store`, `previous_response_id`, and `conversation` are rejected
  before provider forwarding;
- response retrieval, cancel, delete, and input-item listing require explicit
  provider response ownership mapping before they can be implemented;
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
| `input_audio` content parts | Preserved when accepted and within audio count/byte/format caps | Audio input is request input, not audio output, `/v1/audio/*`, Realtime, or a hosted tool. SLAIF forwards only validated raw base64 `data` with `format` `wav` or `mp3`; audio URLs and audio data URLs are rejected in this PR. SLAIF does not fetch, transcribe, decode/rewrite, store/log audio payloads or decoded bytes, or infer final audio billing from bytes or duration |
| `modalities` / `audio` / unsupported non-text content parts | Text-only modality is allowed. Non-streaming audio output is forwarded only with explicit `chat_audio_outputs=true`, valid `audio` config, and configured audio-output pricing metadata. Streaming audio output, `n > 1` with audio output, custom voices, previous-audio references, video fields, alternate image/file/audio part names, file IDs, file URLs, and audio URLs are rejected | SLAIF forwards validated audio-output request fields and preserves non-streaming provider `message.audio` responses without storing/logging generated audio data or transcripts. Audio-output cost is finalized from provider usage/cost; bytes, transcript length, format, voice, and duration are not exact billing units |
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
voices and allowlisted formats, preserves provider `choices[].message.audio`
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

### Streaming Accounting

Streaming has an extra finalization rule because content may already have reached the client:

- Provider chunks are forwarded as they arrive.
- The forwarded chunk surface includes plain text deltas, local/client-side
  function `tool_calls` deltas, `finish_reason="tool_calls"`, provider
  `logprobs` data, and response-format-compatible JSON/text deltas when those
  request fields pass policy.
- Final provider usage is required for success.
- If usage is missing, the reservation is released, a failed/incomplete event is recorded with zero actual cost, a safe SSE error event is emitted, and normal successful `[DONE]` is not emitted.
- If usage is present, the gateway writes a durable provider-completed record before final counter mutation.
- If finalization succeeds, that record is marked finalized and `[DONE]` is emitted.
- If finalization fails, the record is marked with `needs_reconciliation=true` and `recovery_state=provider_completed_finalization_failed`; `[DONE]` is not emitted.
- Operator reconciliation can later finalize these provider-completed rows using stored usage/cost metadata without calling providers.

Streaming does not expand request policy. Hosted/provider-side tools, custom
tools, web search, MCP/connectors, external web access, file/audio content,
non-default `service_tier`, background/provider-state lifecycle
fields, and unknown top-level fields remain rejected before provider
forwarding. Streaming `n > 1` is supported when route metadata explicitly
enables multiple choices; SSE chunks, choice indexes, finish reasons, the final
usage chunk, and `[DONE]` are preserved without buffering the full stream.

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
