# OpenAI Compatibility

This gateway is OpenAI-compatible for the endpoint set implemented in this repository. It is not a full OpenAI platform clone.

Clients use standard OpenAI client configuration only:

```bash
export OPENAI_API_KEY="sk-slaif-..."
export OPENAI_BASE_URL="https://api.ulfe.slaif.si/v1"
```

The key in `OPENAI_API_KEY` is a gateway-issued key. It is not an upstream OpenAI or OpenRouter provider key. The server-side upstream OpenAI secret must use `OPENAI_UPSTREAM_API_KEY`; production validation rejects likely upstream provider keys placed in server `OPENAI_API_KEY`. The gateway authenticates the gateway key, applies policy and quota, resolves a provider route, and substitutes the real provider key server-side before forwarding.

## Endpoint Support

| Endpoint | Status | Auth | Quota/accounting | Streaming | Test coverage |
| --- | --- | --- | --- | --- | --- |
| `GET /v1/models` | Implemented | Required | No usage charge; model visibility is filtered by key policy and enabled routes | Not applicable | Unit and integration coverage for model catalog visibility |
| `POST /v1/chat/completions` | Implemented | Required | PostgreSQL quota reservation before provider call; usage ledger finalization after provider response | Non-streaming and SSE streaming | Unit, integration, and mocked official OpenAI Python client E2E coverage |
| `POST /v1/completions` | Not implemented | Not applicable | Not implemented | Not implemented | Unsupported route/error behavior only; legacy endpoint support requires a separate endpoint, forwarding, accounting, pricing, and test slice |
| `POST /v1/responses` | Not implemented | Not applicable | Not implemented | Not implemented | Unsupported route/error behavior only; planned RC2 scope is limited stateless support under `docs/responses-compatibility.md` |
| `POST /v1/embeddings` | Not implemented | Not applicable | Not implemented | Not implemented | Unsupported route/error behavior only |
| Files endpoints | Not implemented | Not applicable | Not implemented | Not implemented | Unsupported route/error behavior only |
| Images endpoints | Not implemented | Not applicable | Not implemented | Not implemented | Unsupported route/error behavior only |
| Audio endpoints | Not implemented | Not applicable | Not implemented | Not implemented | Unsupported route/error behavior only |
| Native Anthropic API | Not implemented | Not applicable | Not implemented | Not implemented | Anthropic-family model names are covered only through OpenRouter routes |

Unsupported `/v1` routes return OpenAI-shaped errors through the FastAPI error handlers. The gateway does not claim 100% OpenAI platform compatibility outside the rows marked implemented.

## Planned Responses API Scope

`POST /v1/responses` is not implemented in RC1. Responses API support is the
planned RC2 feature family and is constrained by
[`responses-compatibility.md`](responses-compatibility.md).

Planned RC2 support is intentionally narrow:

- stateless `POST /v1/responses` first;
- default-off per key;
- explicit endpoint, model, provider, and tool policy;
- bounded-overrun cost estimates before tool policies are enabled;
- no `background=true`;
- no `store=true` or provider-side response retrieval;
- no `previous_response_id`;
- no `conversation`/provider-side state;
- no MCP/connectors;
- no response delete/cancel/retrieve/list input items initially.

Responses tools must not be blind passthrough. Function tools are the safest
first candidate, web search requires explicit `max_tool_calls` and cost bounds,
and file search/code interpreter require separate pricing, ownership, and audit
treatment before support is claimed.

Endpoint and model permission are separate from capability permission. A key
that is allowed to call `/v1/chat/completions` with a model is not thereby
allowed to use hosted/provider-side tools.

## Model Catalog Visibility

`GET /v1/models` returns an OpenAI-shaped list containing only enabled, visible route metadata allowed for the authenticated gateway key. The endpoint does not call upstream providers and does not create usage or quota records.

Model access follows the same key policy used by chat authorization:

- `allow_all_models=true` exposes otherwise enabled and visible model routes.
- `allow_all_models=false` with a non-empty `allowed_models` list exposes only those allowed model IDs when they are otherwise enabled and visible.
- `allow_all_models=false` with an empty `allowed_models` list returns `{"object": "list", "data": []}`.

This avoids exposing local model catalog entries to keys that cannot use any model.

Operators can seed first-run OpenAI Chat Completions metadata with:

```bash
slaif-gateway bootstrap openai-completions-catalog \
  --pricing-file local-openai-pricing.csv \
  --apply
```

The bootstrap command uses a curated in-repo catalog for `/v1/chat/completions`
only. It does not call OpenAI for discovery, does not fetch pricing, and does
not store provider key values. Legacy `/v1/completions` remains unsupported in
this repository state, so the command rejects `--include-legacy-completions`.
Responses API work is separate and out of scope for this command.
Seeded Chat Completions route rows include explicit `model_routes.capabilities`
metadata under the `chat_completions` key for text chat, streaming, local
function tools, local custom tools, legacy functions, JSON mode, structured outputs, logprobs, and
safe provider usage signals. Hosted tools, multimodal/audio/file inputs,
non-default service tiers, and multiple choices are marked unsupported by
default. Image input to text output requires explicit `chat_image_inputs=true`
metadata; `n > 1` requires explicit `chat_multiple_choices=true` metadata.

## Chat Completions Request Fields

`ChatCompletionRequest` requires `model` and `messages`. The Pydantic schema
continues to preserve extra JSON-compatible fields during parsing so the
gateway can return OpenAI-shaped policy errors instead of silently dropping
client input. Before forwarding, however, the request policy now classifies
every top-level Chat Completions field through a fail-closed registry.

| Field or feature | Current behavior |
| --- | --- |
| `model` | Supported; route resolution later replaces it upstream with the resolved model |
| `messages` | Supported for string content and text content parts within configured count/byte caps; prompts/messages are not stored. User-message `image_url` parts are supported only when route metadata sets `chat_image_inputs=true`; user-message inline `file` parts are supported only when route metadata sets `chat_file_inputs=true` |
| `max_tokens` / `max_completion_tokens` | Gateway-mutated policy fields; validated, defaulted when absent, and rejected when ambiguous or over hard limits |
| `stream` / `stream_options` | Supported; streaming forces `stream_options.include_usage=true` |
| `tools` with `type=function` | Supported local/client-side tool intent within configured count/name/description/schema caps; schemas are forwarded and counted for input estimation |
| `tools` with `type=custom` | Supported only as local/client-side custom tool-call intent when the resolved route explicitly sets `chat_custom_tools=true`; SLAIF does not execute custom tools or police downstream application behavior. Custom tool definitions, format, and grammar are bounded, forwarded, and counted as ordinary input material |
| `functions` / `function_call` | Supported legacy local function fields within equivalent caps and counted for input estimation |
| `tool_choice` | Supported for local function choices and route-enabled named custom choices within configured name/shape caps; hosted/provider-side forced choices are rejected |
| `response_format` | Supported response-shaping field; `text`, `json_object`, and bounded `json_schema` shapes are accepted and counted |
| `metadata` | Supported only as a JSON object within configured key/count/byte caps; forwarded but not stored wholesale |
| `n` | Omitted or `1` works unchanged. `n > 1` is accepted only within `CHAT_MAX_CHOICES_PER_REQUEST` and only when the resolved route explicitly sets `chat_multiple_choices=true`; input is estimated once and possible output reservation is multiplied by `n` |
| `service_tier` | Omitted or `auto` is allowed; non-default values are rejected because pricing is not service-tier aware |
| `prediction` | Supported as a bounded JSON object and counted as provider-context input |
| `modalities` | Allowed only when it requests text only |
| `image_url` message content parts | Supported for image input to text output only on user messages and only with `chat_image_inputs=true`; exact shape is `{ "type": "image_url", "image_url": { "url": "...", "detail"?: "auto" | "low" | "high" } }` |
| `file` message content parts | Supported for inline file input to text output only on user messages and only with `chat_file_inputs=true`; exact accepted first-slice shape is `{ "type": "file", "file": { "filename": "...", "file_data": "<base64>" } }`. Raw base64 is accepted by default; `data:<mime>;base64,...` is accepted only when `CHAT_ALLOW_FILE_DATA_URLS=true`. File IDs and file URLs are rejected |
| `audio`, video/alternate image/file content parts | Rejected until separate audio/broader multimodal pricing and accounting support exists; upstream evidence and the safe implementation roadmap are recorded in [`chat-completions-multimodal-investigation.md`](chat-completions-multimodal-investigation.md) |
| `web_search_options` | Rejected for standard keys; trusted calibration may pass known hosted discovery markers under its bounded policy |
| `background`, `store=true`, `previous_response_id`, `conversation` | Rejected; provider-side lifecycle/state features are not implemented |
| Unknown top-level fields | Rejected in standard and trusted-calibration modes with `unknown_chat_completion_field` |

Current request policy also rejects malformed or empty `messages`, too many or
oversized messages/text/image/file parts, invalid image URLs or data URLs,
invalid image detail values, invalid file data, filenames, file IDs, file URLs,
invalid scalar controls, invalid output-token
controls, input estimates over the configured hard input cap, non-object or
oversized `stream_options`, overlarge `stop`, `user`, `logit_bias`,
`metadata`, `prediction`, function-tool schema, and `response_format` schema
payloads, and invalid or over-cap Chat Completions `n` values. Rejection
messages name the field and problem without echoing raw messages, metadata
values, image URLs, image/file base64 data, filenames, file IDs, schemas, tool
payloads, or request bodies.

Current Chat Completions capability policy allows local/client-side function
tools, route-enabled non-streaming local custom tools, route-enabled image
input to text output, route-enabled inline file input to text output, legacy
`functions` / `function_call`, `response_format`, JSON mode, bounded multiple
choices, and ordinary streaming. SLAIF does not
police what a downstream application does
when it receives a local function-tool or custom-tool call from the model.
Hosted/provider-side tools are denied by default because there is no persisted
hosted-tool allowlist:
`web_search_options`, `web_search`, `web_search_preview`, `file_search`,
`code_interpreter`, `computer` / `computer_use`, `image_generation`,
`tool_search`, MCP/connectors, provider-side connector/authorization markers,
unknown tool types, `background=true`, `external_web_access`, and
search-specific Chat Completions models such as `gpt-5-search-api` are rejected
before Redis rate limiting, route resolution, pricing lookup, quota
reservation, or provider forwarding.

Trusted calibration keys are the discovery exception. A trusted organizer/admin
key in `trusted_calibration_discovery` mode may pass routed Chat Completions
hosted-capability markers only when the local route metadata explicitly allows
the matching hosted capability, so SLAIF can observe safe usage metadata.
Normal keys keep the hosted-tool-deny behavior even if a route advertises
provider support. Calibration mode does not implement `/v1/responses` or
`/v1/completions`, does not create routes automatically, and still denies
external MCP/connectors, provider-side authorization, connector IDs, server
URLs, approval flows, and background/provider-state lifecycle features by
default.

Route/model capability metadata is a separate gate from key endpoint/model and
provider allowlists. After route resolution and before Redis rate limiting,
pricing lookup, PostgreSQL quota reservation, or provider forwarding, the
gateway checks the resolved route's `chat_completions` capability metadata
against the accepted request shape. Text chat, streaming, local function tools,
local custom tools, image input, legacy functions, JSON mode, structured
outputs, logprobs, reasoning controls, image input, file input, and multiple choices must be allowed by
the route metadata when used.
A model allowlist
entry alone therefore does not imply permission to use those capabilities.
Existing routes that predate the capability block use a documented
compatibility fallback matching the previously supported Chat Completions
surface, but newly seeded and newly created Chat Completions routes receive
explicit metadata. Malformed or unknown `chat_completions` capability flags fail
closed.

Chat Completions input-token and cost pre-reservation uses a conservative local
estimate over message content plus serialized non-message provider-forwarded
object/list fields such as local function/custom `tools`, legacy `functions`, object-shaped
`tool_choice` / `function_call`, `response_format` JSON schemas,
`prediction`, `metadata`, `logit_bias`, and `stream_options`. Rejected unknown
or over-cap fields do not reach estimation or provider forwarding. Very large
tool/function/schema payloads may be rejected by explicit per-field caps before
the broader hard input-token cap is evaluated. The estimate is intentionally
conservative and may over-reserve; successful accounting still finalizes from
actual provider usage when available. This is Chat Completions remediation and
does not implement the Responses API.

Chat Completions custom tools use ordinary Chat Completions accounting only.
SLAIF adds no custom-tool billing category, pricing rule, execution fee, or
ledger cost column. Custom tool definitions and grammar can increase ordinary
input-token estimates; generated custom-tool input can increase ordinary output
tokens. If the downstream app later sends tool results back to the gateway,
that is a separate ordinary request.

Streaming custom tools are intentionally unsupported in this release. The
current installed official OpenAI Python SDK exposes non-streaming Chat
Completions custom tool request/response types, but its Chat Completions stream
chunk type only models function tool deltas. Requests with `stream=true` and
custom tools fail before provider forwarding.

Chat Completions image input to text output is implemented as the first narrow
multimodal slice. SLAIF supports remote `http`/`https` image URLs and base64
`data:image/png|jpeg|webp|gif;base64,...` image data URLs behind explicit
`chat_image_inputs=true` route capability and configured count/byte caps.
SLAIF does not fetch remote image URLs, decode image pixels, rewrite image
payloads, store or log image URLs/base64 data, infer exact image cost from
bytes, or enable image generation. Image input composes with streaming text
output, `n > 1`, local function tools, non-streaming custom tools,
`response_format`, and logprobs only when those features' own capabilities and
policies pass. Final accounting still uses provider usage/cost once.

Chat Completions inline file input to text output is implemented as the second
narrow multimodal slice. SLAIF supports user-message file parts with `filename`
and inline `file_data` only behind explicit `chat_file_inputs=true` route
capability and configured count/byte/type caps. Raw base64 file data is
accepted by default; data URLs are opt-in with MIME validation. SLAIF rejects
`file_id` until a Files API ownership/audit/cleanup policy exists, rejects file
URLs, does not fetch or upload files, does not store/log filenames or file
payloads, and does not infer exact file cost from bytes. File input composes
with streaming text output, `n > 1`, image input, local function tools,
non-streaming custom tools, `response_format`, and logprobs only when those
features' own capabilities and policies pass. Final accounting still uses
provider usage/cost once.

Chat Completions audio input and audio output remain unsupported. OpenAI and
OpenRouter document those request/response surfaces for compatible models, but
SLAIF keeps them disabled until separate route capabilities, request-size and
format caps, modality estimation, pricing/catalog support, provider usage
parsing, accounting tests, provider adapter tests, official-client E2E
coverage, and redaction/no-storage tests are implemented. See
[`chat-completions-multimodal-investigation.md`](chat-completions-multimodal-investigation.md).

`n > 1` is supported as bounded multiple-choice Chat Completions only when the
resolved route explicitly sets `chat_multiple_choices=true`. The configured
gateway maximum is `CHAT_MAX_CHOICES_PER_REQUEST` (default `4`). The effective
max output-token control remains a per-choice request cap; admission-time
reservation and estimated output cost use `effective_max_output_tokens_per_choice
* n`. Input tokens and input cost are estimated once for the single request.
Final accounting uses provider-reported total usage or provider-reported cost
once and does not multiply `completion_tokens` or OpenRouter cost again by `n`.
One request remains one reservation and one usage-ledger event.

## Gateway-Mutated Fields

| Field | Behavior | Reason |
| --- | --- | --- |
| `model` | Replaced upstream with the resolved route `upstream_model` | Allows aliases and provider-specific model names while keeping client-facing model IDs stable |
| `max_completion_tokens` | Injected from `DEFAULT_MAX_OUTPUT_TOKENS` when both output-token fields are absent | Hard quota requires a bounded maximum output |
| `max_tokens` / `max_completion_tokens` | Rejected when both are present with different values; rejected when non-positive or over `HARD_MAX_OUTPUT_TOKENS` | Avoid ambiguous quota estimation and enforce hard output caps |
| `stream_options.include_usage` | Forced to `true` for streaming requests, preserving other `stream_options` keys | Streaming accounting requires final provider usage metadata |
| Gateway-internal fields | Not sent upstream | Internal accounting, routing, and quota metadata never belongs in the provider body |

Non-streaming requests do not get `stream_options` injected unless the client supplied it. Streaming requests always forward `stream=true` and `stream_options.include_usage=true`.

## Request Pipeline

For `POST /v1/chat/completions`, the implemented order is:

1. Authenticate the gateway key from `Authorization: Bearer ...`.
2. Check endpoint allow-list policy.
3. Validate request shape with the permissive Chat Completions schema.
4. Apply request field policy, hosted-tool policy, request caps, and token caps,
   including serialized non-message provider-forwarded Chat Completions fields
   in the input estimate.
5. Resolve the model route/provider and enforce explicit route/model
   Chat Completions capability metadata.
6. Apply Redis operational rate limits when enabled.
7. Look up pricing and FX data.
8. Reserve PostgreSQL hard quota.
9. Forward to OpenAI or OpenRouter.
10. Parse provider usage.
11. Finalize or release accounting.
12. Record metrics, safe usage ledger metadata, and advisory Chat
    Completions usage-profile metadata when final usage is available.

Usage-profile rows are safe calibration-foundation metadata only. They do not
store prompts, completions, messages, raw request bodies, raw response bodies,
full provider URLs, tool schemas, tool arguments, tool results, raw
chain-of-thought, provider keys, gateway plaintext keys, token hashes,
encrypted payloads, nonces, password hashes, session tokens, or email bodies.
They are not invoice-grade provider billing truth and do not implement
`/v1/responses`.

Trusted calibration usage can be summarized from the CLI or admin dashboard to
preview strict participant policy values. The preview is advisory and
non-mutating: it does not create key templates, participant keys, or gateway key
policy changes, and it does not make additional provider calls.

Redis rate limiting is temporary operational throttling only. PostgreSQL remains authoritative for hard quota and usage accounting.
Chat Completions billing is an admission-time budget check plus post-call spend
accounting. It is not hard real-time spend interruption inside one upstream
call. If a request is admitted under the current balance, final provider usage
is still finalized even when the actual token or cost usage exceeds the
pre-call reservation. The usage ledger records safe `reservation_overrun`,
`token_reservation_overrun`, `cost_reservation_overrun`, `reserved_*`,
`actual_*`, and overrun-policy metadata. A finalized call may therefore leave a
key above its configured local limits or with a negative remaining balance;
subsequent calls are blocked by the normal PostgreSQL quota admission checks
until limits are raised, usage is reset, or the key otherwise becomes compliant
again.

Actual Chat Completions cost finalization uses safe component-aware metadata:
cached input tokens use `cached_input_price_per_1m` when available and otherwise
fall back to ordinary input pricing with reduced cost confidence; reasoning
tokens are treated as part of output tokens for current Chat Completions and use
`reasoning_price_per_1m` for the reasoning subset when configured, otherwise
ordinary output pricing with reduced confidence. OpenRouter provider-reported
cost is preferred for actual finalization when the provider returns a valid
non-negative cost and supported currency; the SLAIF-calculated cost is retained
as comparison metadata. OpenAI requests use SLAIF-calculated cost unless an
explicitly supported provider-reported cost path is added later. These values
are SLAIF local accounting assumptions, not provider invoice certification.

## Streaming Compatibility

Streaming Chat Completions use Server-Sent Events and are compatible with the official OpenAI Python client `stream=True` path in mocked E2E tests.

Implemented streaming behavior:

- The gateway returns `text/event-stream`.
- Provider SSE data chunks are forwarded as they arrive for accepted Chat
  Completions shapes, including plain text deltas, local `function`
  `tool_calls` deltas, `finish_reason="tool_calls"`, and OpenAI-compatible
  `logprobs` payloads when the provider sends them.
- Streaming requests with `response_format={"type":"json_object"}` or bounded
  `response_format={"type":"json_schema", ...}` are accepted by the same
  request policy as non-streaming requests. The gateway does not parse or store
  structured output content; provider chunks remain SSE data.
- Upstream streaming requests use `Accept: text/event-stream`.
- The gateway forces `stream_options.include_usage=true`.
- Final provider usage is required for successful streaming accounting finalization.
- The provider `[DONE]` event is held until finalization succeeds.
- Provider streaming error events are converted to safe OpenAI-shaped SSE error
  events or sanitized diagnostics; raw provider bodies, prompts, local tool
  argument fragments, schemas, and secrets are not returned from diagnostics.
- If final usage is missing, the gateway records a failed/incomplete accounting event, releases the reservation according to current policy, does not charge actual cost, emits a safe SSE error event, and does not emit a normal successful `[DONE]`.
- If the provider completed with usage but finalization fails after content was already delivered, the gateway leaves a durable provider-completed recovery row marked for reconciliation and does not treat the request as a zero-cost provider failure.
- Streaming Redis concurrency slots are heartbeated while the stream remains open and released in the generator cleanup path.

Unsupported streaming request features are the same as non-streaming Chat
Completions: hosted/provider-side tools, web search, custom tools,
multimodal/audio/file inputs, non-default `service_tier`, background
or provider-state lifecycle fields, MCP/connectors, external web access, and
unknown top-level fields are rejected before provider forwarding.
Streaming `n > 1` is supported for routes with `chat_multiple_choices=true`;
provider SSE chunks are passed through without buffering, including chunks with
multiple `choices`, interleaved choice indexes, and the final empty-choices
usage chunk.

Client disconnect handling is best-effort through generator cancellation cleanup. The code records a provider failure for detected cancellation, releases the quota reservation, and releases rate-limit concurrency when Redis rate limits are enabled. A real ASGI server test closes a stream early and verifies this cleanup path.

Successful text and local function/tool-call streaming are covered by mocked
official OpenAI Python client E2E tests. The missing-final-usage error path is
covered by unit and PostgreSQL integration tests; an additional official-client
assertion for the exact exception shape can be added later if needed.

## Error Compatibility

Errors from `/v1` routes are OpenAI-shaped:

```json
{
  "error": {
    "message": "...",
    "type": "invalid_request_error",
    "param": null,
    "code": "..."
  }
}
```

Provider errors are normalized to safe OpenAI-shaped client errors. Raw provider response bodies are not returned to clients and are not stored. When available, bounded sanitized provider diagnostics are stored for operators in failure ledger metadata.

Unsupported endpoints and unsupported provider adapter endpoints are explicit errors; they are not silently proxied.

## What Is Not Implemented

- Responses API in RC1. It is planned for RC2 under
  `docs/responses-compatibility.md`, with stateful/background/provider-side
  storage features and MCP excluded from the initial scope.
- Hosted/provider-side tool support for normal participant keys. Local function
  tools remain allowed as ordinary client-side behavior. Trusted calibration
  keys can use broad discovery policy only for routed Chat Completions requests.
- Embeddings API.
- Files, images, audio, or batch endpoints.
- Native Anthropic API.
- New provider types beyond OpenAI and OpenRouter.
- Bulk key send-now execution, owner/institution/cohort delete or anonymization workflows,
  usage/audit mutation pages beyond CSV exports, and MFA remain outside the current admin surface.
  Bulk key import preview/execution and owner/institution/cohort create/edit pages are
  admin metadata workflows only.
  Route import preview/execution and pricing import preview/execution are admin
  metadata workflows. FX import preview/execution is also admin metadata:
  preview is no-mutation, execution is confirmed create-only local metadata
  mutation, and neither path calls external FX APIs or providers. They do not
  change `/v1` request/response compatibility.
  Docker/Nginx packaging is deployment documentation and service layout only; it
  does not change `/v1` compatibility. The implemented dashboard and key-email
  delivery workflows are summarized in `docs/compatibility-matrix.md` and
  `docs/security-model.md`.
- Automatic key-email sending by default. Key email delivery is explicit through
  create/rotate email modes, CLI commands, or the one-time-secret-backed email
  delivery detail actions.
- Real upstream smoke tests in the normal test suite.
