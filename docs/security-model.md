# Security Model

This document summarizes the implemented security architecture. It is not a
formal certification, compliance audit, or penetration-test report.

For operational response procedures, see the
[`runbooks`](runbooks/README.md), especially provider key rotation, gateway key
leak response, HMAC secret rotation, one-time-secret encryption key handling,
database restore, reconciliation, Redis outage, PostgreSQL readiness, ambiguous
email delivery, and admin access runbooks.

## Goals

- Reduce damage from gateway bearer key leakage.
- Keep upstream provider keys isolated from clients.
- Enforce hard quota and account for usage before and after provider calls.
- Avoid storing prompts and completions by default.
- Avoid placing plaintext gateway keys in PostgreSQL, audit rows, logs,
  email-delivery metadata, or Celery/Redis payloads.

## Gateway Key Lifecycle

The gateway generates OpenAI-looking bearer keys with a configurable prefix,
such as `sk-slaif-`. The `public_key_id` portion is non-secret and supports fast
lookup.

The full plaintext key is shown, written, or delivered only during creation or
rotation. PostgreSQL stores an HMAC-SHA-256 digest of the full key using the
configured server-side HMAC secret version. Key verification recomputes the HMAC
for the stored version and compares it without storing plaintext.

`ACTIVE_HMAC_KEY_VERSION` selects the version used for newly generated keys.
Existing keys continue to require the HMAC secret version stored on the key row.
If a key is lost, rotate it; do not resend an old plaintext key.

## Provider Key Isolation

Provider secrets live in environment variables or deployment secrets. The
`provider_configs` table stores provider metadata and environment variable names,
not secret values. Admin provider config forms accept `api_key_env_var` names
only and reject provider-secret-looking values; they never accept, store, or
display provider key values.

In production, enabled built-in OpenAI/OpenRouter providers require configured,
non-placeholder upstream provider secrets. The server treats `OPENAI_API_KEY` as
a client-facing gateway-key variable, not as the upstream OpenAI provider secret;
likely provider-key values in `OPENAI_API_KEY` fail configuration validation
with a safe message that names `OPENAI_UPSTREAM_API_KEY` but never logs the
value. Production `/readyz` checks enabled DB provider config env-var references
and reports only env var names, never secret values.

Client `Authorization` headers contain gateway-issued keys and are never
forwarded upstream. Provider adapters construct a new upstream `Authorization`
header from the server-side provider secret and use an outbound header allowlist.
Provider-bound JSON request bodies are also reconstructed inside the gateway
from validated, capped, capability-approved fields. The gateway does not forward
the raw client request dictionary upstream or rely on removing a few denied
fields from an otherwise unknown body. The only approved provider-body
construction path is an endpoint-specific normalized upstream request contract
followed by the canonical upstream payload builder.

Responses structured text output follows the same boundary. JSON object mode
and JSON schema `text.format` payloads are text-output constraints, not tools or
hosted authority. JSON schemas are allowed only at the explicit
`text.format.schema` path, require route/model capability metadata, are capped
and counted for input estimation, and must not be stored or logged alongside
Responses input text, output text, raw request bodies, raw response bodies, or
provider event bodies.

Responses input item arrays follow the same boundary. They are accepted as
stateless message input with supported roles and string or `input_text` content
parts. User-message `input_image` URL/data URL parts require explicit
route/model `capabilities.responses.image_input=true` metadata, are capped, and
are counted for conservative admission estimates. SLAIF does not fetch image
URLs, decode image pixels, rewrite data URLs, store/log raw image URLs, image
data URLs, or base64 payloads, or treat image bytes as invoice-grade billing
truth. String-only `function_call_output` and `custom_tool_call_output` items
are accepted as ordinary stateless input for local-tool follow-up requests.
Function-call/custom-tool-call items, reasoning/stateful items, hosted-tool
items, `input_image.file_id`, file content parts, and audio content parts are
rejected before provider forwarding. Input item text and string tool outputs
are counted for admission estimates but are not stored or logged.

Responses local function tools follow the same boundary. They require explicit
route/model `capabilities.responses.function_tools=true` metadata and are
canonicalized from bounded `tools[].type=function` definitions. Function
schemas are opaque only inside `tools[].parameters`, are capped and counted as
ordinary input material, and are not stored or logged. SLAIF does not execute
functions, does not add special tool billing, and does not enable hosted tools,
MCP/connectors, web search, file search, code interpreter, computer use, image
generation, tool search, storage, or background mode through this capability.

Responses local custom tools follow the same boundary. They require explicit
route/model `capabilities.responses.custom_tools=true` metadata and are
canonicalized from bounded `tools[].type=custom` definitions with optional text
or grammar format. Custom grammar definitions and string-only
`custom_tool_call_output` items are ordinary input material for admission
estimates and are not stored or logged. SLAIF does not execute custom tools,
inspect or store generated custom-tool input, add special tool billing, or
enable hosted tools, MCP/connectors, web search, file search, code interpreter,
shell/apply-patch/local environments, computer use, image generation, tool
search, storage, or background mode through this capability.

## Chat Completions Capability Policy

SLAIF permissions are endpoint, model, provider, capability/tool,
request-shape, and accounting/data-policy permissions. A model allowlist or
`/v1/chat/completions` endpoint allowlist does not grant local function-tool,
structured-output, logprobs, reasoning-control, hosted-tool, or service-tier
permission by itself.

Current Chat Completions policy allows local/client-side `function` tools,
route-enabled non-streaming local/client-side `custom` tools, legacy
`functions` / `function_call`, `response_format`, JSON mode, and ordinary
streaming. SLAIF does not execute local tools and does not police what a
downstream application does when it receives a local function or custom tool
call.

The Chat Completions field registry is fail-closed. Endpoint and model
authorization do not authorize unknown future request features. Standard keys
and trusted calibration keys reject unknown top-level fields before Redis rate
limiting, route resolution, pricing lookup, PostgreSQL quota reservation,
usage-profile insertion, or provider forwarding. The error includes the field
name as a safe `param`, but not the raw value. Current policy also rejects
custom tools and multiple choices when route metadata does not explicitly
enable them, non-default `service_tier`, audio/image/file/video content,
provider-side lifecycle/state fields, and other unclassified feature-bearing
fields until pricing, accounting, forwarding, and tests exist.

OpenAI upstream evidence for Chat Completions custom tools is tracked in
[`chat-completions-custom-tools-investigation.md`](chat-completions-custom-tools-investigation.md).
SLAIF supports the documented non-streaming request/response shapes only as
local/client-side intent. Custom tool definitions and generated custom-tool
input are ordinary token-bearing Chat Completions material. SLAIF adds no
custom-tool pricing, execution fee, or custom-tool ledger billing columns, and
a later downstream app call with tool results is a separate ordinary gateway
request. Custom tools are not provider-hosted execution authority.

OpenAI and OpenRouter upstream evidence for Chat Completions image/audio/file
surfaces is tracked in
[`chat-completions-multimodal-investigation.md`](chat-completions-multimodal-investigation.md).
Image input, inline file input, and audio input to text output are enabled only
behind explicit route capability flags. Base64 image/audio/file payloads,
external URLs, uploaded file IDs, filenames, audio response bytes, and parsed
file contents can contain personal data or secrets and must not be stored or
logged.
SLAIF may forward bounded image URLs when `chat_image_inputs=true`, but it does
not fetch them. SLAIF does not forward file URLs, file IDs, or audio URLs in
this release. Forwarding any external image URL is provider-side URL fetching,
not hosted web search, but file/audio URL forwarding still needs explicit
privacy and egress policy before support is enabled.

Supported Chat Completions fields are validated against explicit type, range,
count, and byte caps before Redis rate limiting, route resolution, pricing
lookup, PostgreSQL quota reservation, usage-profile insertion, or provider
forwarding. The cap layer keeps local function tools allowed but bounds tool
count, function name and description length, per-tool schema size, and total
schema size. It also bounds custom tool count, name/description, serialized
format, and grammar definition sizes. It also bounds message count/content,
text parts, image part count, remote image URL bytes, base64 image data URL
bytes, inline file part count, file data bytes, filename bytes, allowed file
extensions/MIME types, audio input count, audio data bytes, allowed audio
formats, audio-output format/voice values, `response_format` schemas,
`metadata`, `prediction`, `stream_options`, `stop`, `user`, `n`, and
`logit_bias`. Errors name the field
and policy problem without logging or returning raw messages, prompt content,
image URLs, base64 image/file/audio payloads, filenames, file IDs, file URLs,
generated audio data, transcripts, metadata values, schemas, tool arguments,
provider keys, gateway keys, cookies, sessions, CSRF tokens, encrypted payloads,
or nonces.

Resolved Chat Completions routes are also checked against explicit
`model_routes.capabilities["chat_completions"]` metadata. New seeded or
manually created Chat Completions routes receive conservative capability flags
for the currently supported surface: text chat, streaming, local function tools,
local custom tools, legacy functions, JSON mode, structured outputs, logprobs, reasoning/cached
usage signals, and explicit false flags for hosted tools, multimodal/audio/file
surfaces, non-default service tiers, and multiple choices. Image input is allowed
only with `chat_image_inputs=true`; that flag does not imply hosted tools,
image generation, file input, audio input, audio output, custom tools, function
tools, `n > 1`, non-default service tiers, or Responses support. Inline file
input is allowed only with `chat_file_inputs=true`; that flag does not imply
`/v1/files`, file IDs, file URLs, hosted file search, retrieval, code
interpreter, image input, audio input, audio output, custom tools, function
tools, `n > 1`, non-default service tiers, or Responses support. Audio input is
allowed only with `chat_audio_inputs=true`; that flag does not imply audio
output, top-level audio modalities, `/v1/audio/*`, Realtime, image/file input,
custom tools, function tools, `n > 1`, non-default service tiers, or Responses
support. Non-streaming audio output is allowed only with
`chat_audio_outputs=true` and configured audio-output pricing metadata; that
flag does not imply audio input, `/v1/audio/*`, Realtime, streaming audio
output, custom voices, previous-audio references, hosted tools, custom tools,
function tools, `n > 1`, non-default service tiers, or Responses support.
Multiple choices are only allowed with `chat_multiple_choices=true`;
that flag does not imply hosted tools, custom tools, multimodal support, audio
output, non-default service tiers, or Responses support. Route capability checks
happen after route resolution and before Redis rate limiting, pricing lookup,
PostgreSQL quota reservation, usage-profile insertion, or provider forwarding.
Existing routes without a `chat_completions` block use a documented
compatibility fallback for the previously supported surface; malformed or
unknown Chat Completions capability flags fail closed.

Hosted/provider-side tools are denied by default because no persisted per-key
hosted-tool policy exists. Chat Completions requests with `web_search_options`,
`web_search`, `web_search_preview`, `file_search`, `code_interpreter`,
`computer` / `computer_use`, `image_generation`, `tool_search`, MCP/connectors,
provider-side `server_url`, `connector_id`, `authorization`, or
`require_approval` markers, unknown tool types, `background=true`,
`external_web_access`, or search-specific models such as `gpt-5-search-api` are
rejected before Redis rate limiting, route resolution, pricing lookup,
PostgreSQL quota reservation, usage-profile insertion, or provider forwarding.
The rejection path returns OpenAI-shaped errors and does not log raw request
bodies, prompts, completions, tool schemas, provider keys, gateway keys,
cookies, sessions, CSRF tokens, encrypted payloads, or nonces.

Trusted calibration keys are the narrow exception for discovery. They are real
gateway keys, created through the CLI or admin key creation page only with
explicit confirmation, a short validity window, and a small request limit. They
still use normal authentication, route
resolution, provider-secret isolation, PostgreSQL request reservation and
finalization, usage ledger, usage profiling, and audit behavior. Their
`trusted_calibration_discovery` mode may pass hosted/provider-side Chat
Completions capability markers only when the resolved route metadata
explicitly allows that hosted capability, so a trusted organizer can discover
workflow requirements, but it still denies unsupported endpoints, external
MCP/connectors, provider-side authorization, connector IDs, server URLs,
approval flows, and background/provider-state lifecycle features by default.
Calibration keys are not participant keys.

## Admin OpenAI Assisted Proposal Boundary

OpenAI-assisted catalog proposal generation is an admin-only operator workflow,
not a gateway user endpoint. It can call OpenAI only when an authenticated admin
explicitly runs the CLI command with the risk acknowledgement or submits the
dashboard proposal form with CSRF and the required acknowledgement checkbox.

The workflow uses the separate `OPENAI_ADMIN_DISCOVERY_API_KEY` environment
variable by default. It does not use `OPENAI_API_KEY`, does not read
`provider_configs` secret values, and never displays or logs the discovery key
value. It asks OpenAI for strict JSON from official OpenAI source URLs, validates
the JSON locally, and renders reviewed TSV proposal content only.

Proposal generation does not mutate `pricing_rules` or `model_routes`; the
existing import preview/confirm/audit pages remain the only mutation gate. Safe
audit/log events may include admin ID, proposal kind, source URLs, proposal
model, row count, warning count, and a diagnostic ID. They must not include raw
model responses, raw webpage text, prompts, completions, cookies, sessions, CSRF
tokens, provider keys, encrypted payloads, nonces, raw request/response bodies,
or generated full TSV content.

The dashboard may submit the final validated TSV from the proposal result page
to the existing pricing or route import preview route. That bridge is
CSRF-protected, preview-only, and subject to the normal import byte limits. It
does not store generated TSV in PostgreSQL, audit rows, cookies, or server-side
admin sessions, and it does not bypass unknown-field, secret-looking-value,
duplicate, conflict, unsupported-row, or update-classification checks.

## Quota And Accounting

PostgreSQL is the hard quota source of truth. Redis rate limiting is operational
throttling only.

For supported `/v1/chat/completions` requests, the gateway authenticates the key,
checks policy, estimates input/output/cost, reserves PostgreSQL quota before
forwarding, forwards the request, then finalizes or releases the reservation
after provider response/error handling.

Chat Completions billing is an admission-time budget check plus post-call spend
accounting. For `stream=true`, the per-key Streaming Live-Burn Margin feature
adds a provisional operational brake that can interrupt a Chat Completions
stream when estimated live burn crosses the configured cost or token cutoff.
This is not invoice-grade billing truth and does not replace PostgreSQL hard
quota. If a successful provider response reports actual tokens or cost above
the reservation, SLAIF finalizes the actual usage, marks the reservation
finalized, updates used counters, and records safe overrun metadata in the
usage ledger. That may leave a key above its configured local limits or with
negative remaining balance. Subsequent calls are then blocked by normal
PostgreSQL quota admission checks until limits are raised, usage is reset, or
the key otherwise becomes compliant.

The usage ledger records metadata, token counts, cost, provider/model status,
and safe diagnostics. It does not store prompt text, completion text, uploaded
files, tool payloads, or raw provider bodies by default.

Current Chat Completions requests also create advisory `usage_profiles` rows
after successful accounting finalization when safe metadata is available. These
rows support future calibration-key and key-template recommendation workflows;
they are not invoice-grade billing truth. They store gateway endpoint path,
provider, requested/resolved model, sanitized provider host/path, token counts,
safe tool counts/function names, provider-reported cost when exposed, and
SLAIF-calculated local cost. Missing provider metrics remain `null`/`unknown`
instead of guessed. Usage profiles do not store prompts, completions, messages,
raw request bodies, raw response bodies, full URLs with query strings/fragments,
credentials, provider keys, plaintext gateway keys, token hashes, encrypted
payloads, nonces, password hashes, session tokens, email bodies, raw
chain-of-thought, tool schemas, tool arguments, or tool results. This is Chat
Completions-only RC2 foundation work; it does not implement Responses API.
For trusted calibration requests, usage-profile metadata may include safe
provenance such as `key_purpose`, `capability_policy_mode`, and observed hosted
capability type names. It still must not include raw tool schemas, arguments,
results, prompts, completions, raw bodies, or secrets.

Admins may summarize trusted calibration-key usage from the CLI or dashboard.
That preview reads safe `usage_profiles` rows only and proposes strict
participant policy values with an explicit multiplier. It is non-mutating: it
does not create participant keys, does not change gateway key policy, and does
not update routes or pricing. After review, admins may create a durable
versioned key template from the proposal with confirmation and an audit reason.
Template creation mutates only `key_templates`, `key_template_revisions`, and
safe audit metadata. It does not create participant keys, mutate existing
gateway keys, or apply policy updates. Hosted capabilities observed during
calibration are stored as review-required rather than silently enabled for
normal participant keys; external MCP/connectors remain denied by default.
Admins may also create one normal standard gateway key from a selected
immutable template revision. That workflow uses normal key creation, records
template provenance on the key, and does not mutate existing keys or template
revisions. Bulk participant-key generation remains future work.

Quota, accounting, and reconciliation are covered by invariant-oriented unit
and PostgreSQL tests. The coverage checks that reserved and used counters do not
go negative, repeated release/finalization/reconciliation attempts do not
double-subtract or double-charge, provider-completed usage remains recoverable
after finalization failures, and ledger/audit metadata omits prompt,
completion, raw request/response, key, token-hash, encrypted-payload, nonce,
password-hash, and session-token material. These tests are defense-in-depth and
are not formal verification.

Manual reconciliation exists for expired pending reservations and
provider-completed streaming finalization failures. Provider-completed repair
uses stored safe usage/cost metadata and does not call providers.

Operator procedures are documented in
[`runbooks/stale-reservation-reconciliation.md`](runbooks/stale-reservation-reconciliation.md)
and [`runbooks/provider-completed-reconciliation.md`](runbooks/provider-completed-reconciliation.md).

Celery/Celery Beat can be configured to inspect reconciliation backlog
periodically. Scheduled reconciliation is disabled by default and scheduled
mutation remains opt-in: expired-reservation and provider-completed repair tasks
only execute when the matching auto-execute setting is enabled and dry-run mode
is disabled. Scheduled tasks call the same reconciliation service used by the
CLI, never call providers, and return/log only low-cardinality counts plus safe
IDs and statuses. They do not include plaintext gateway keys, token hashes,
encrypted payloads, nonces, provider keys, prompts, completions, or email bodies
in task payloads/results.

Optional reconciliation alert webhooks are disabled by default and are emitted
only from backlog inspection. Alerting is for operator visibility, not repair:
it does not mutate quota/accounting, does not call providers, and does not send
email. Payloads contain counts by default; when explicitly enabled they may also
include safe reservation or usage-ledger IDs. Webhook URLs may contain bearer
tokens or routing secrets and must be treated as secrets; logs and task results
must not include the full webhook URL.

## Streaming Security And Accounting

Streaming requests force `stream_options.include_usage=true` upstream so final
usage can be captured. Successful streaming requires final provider usage before
the gateway emits a successful `[DONE]`.

For accepted Chat Completions requests, the gateway forwards provider SSE data
chunks without buffering the full stream. This includes plain text deltas,
local/client-side function `tool_calls` deltas, `finish_reason="tool_calls"`,
provider `logprobs` data, and structured-output-compatible chunks when the
request passes the same field registry, capability policy, and cap validation
as non-streaming requests. Streaming `n > 1` preserves provider choice indexes
and final usage chunks without buffering. Streaming does not enable hosted
tools, custom tools, web search, audio output, non-default
`service_tier`, background/provider-state features, MCP/connectors, or unknown
top-level fields.

If final usage is missing, the gateway emits a safe stream error, records the
request as incomplete/failed according to current accounting policy, and does not
emit a normal successful `[DONE]`. If final usage was received but finalization
fails after content reached the client, a durable recovery state is left for
operator reconciliation.

Prompt/completion content, local tool argument fragments, function schemas,
response-format schemas, metadata values, raw request/response bodies, gateway
keys, provider keys, Authorization headers, cookies, CSRF/session tokens, and
encrypted payloads are not stored or logged by streaming diagnostics.

Chat Completions streaming live-burn monitoring is implemented only for
`POST /v1/chat/completions` with `stream=true`. It estimates visible generated
text deltas, including function tool-call name/argument deltas, counts them,
and discards the text. It may store only safe provisional counters and
low-cardinality metadata; it must not store prompt text, completion text,
streamed chunk text, tool arguments or outputs, media payloads, raw request
bodies, provider keys, gateway plaintext keys, Authorization headers, cookies,
CSRF/session tokens, encrypted payloads, or nonces. PostgreSQL remains
authoritative for hard quota/accounting, Redis and in-memory live state remain
temporary operational state only, and provider final usage/cost remains
authoritative when available. Responses live-burn monitoring remains future
work under [`streaming-live-burn-margin.md`](streaming-live-burn-margin.md).

## Chat Completions Non-Message Input Estimation

Chat Completions request policy estimates input tokens before Redis rate
limiting, route resolution, pricing lookup, PostgreSQL quota reservation, or
provider forwarding. The estimate includes message content plus conservative
canonical JSON byte-size upper bounds for serialized non-message object/list
fields that are forwarded to providers, including local function/custom `tools`, `functions`,
object-shaped `tool_choice` / `function_call`, `response_format` JSON schemas,
`prediction`, `metadata`, `logit_bias`, and `stream_options`. Unknown top-level
fields and over-cap fields are rejected before this estimation step and are not
forwarded.

Large tool/function/schema payloads may be rejected before provider calls. The
estimator stores and exposes only safe count metadata such as token estimate,
counted field names, and counted bytes. It does not store prompts, completions,
raw request bodies, raw response bodies, raw tool/schema/custom-tool/grammar payloads, provider
keys, plaintext gateway keys, token hashes, encrypted payloads, nonces,
password hashes, session tokens, or email bodies. Successful requests still
finalize accounting from actual provider usage when available. This is Chat
Completions hardening only; it does not implement Responses API behavior.

## Responses API Security Model

Responses API support is limited to stateless text-output `POST /v1/responses`
with string input or bounded input item arrays, route-enabled user-message
image URL/data URL input, route-enabled user-message file URL/data URL input,
non-streaming JSON, typed SSE streaming, non-streaming local function tools,
and non-streaming local custom tools. `POST /v1/responses/input_tokens` is a
separate provider-reported count endpoint for the same stateless local input
subset. It is default-off and policy-first:

- Responses generation must be explicitly enabled per key through the
  `/v1/responses` endpoint allowlist. Input-token counting must be explicitly
  enabled through `/v1/responses/input_tokens`; `/v1/responses` alone does not
  imply it.
- Endpoint, model, provider, and tool allowlists all apply.
- Route/model metadata must explicitly advertise Responses text/stateless
  capability; Chat Completions capabilities do not imply Responses capability.
- Streaming also requires explicit Responses streaming capability and route
  streaming support. Typed provider events are forwarded without storing
  streamed deltas, and final accounting uses provider usage from the completed
  response event. The completed event, and any upstream `data: [DONE]` marker if
  present, are not emitted as normal success until usage-backed finalization
  succeeds. Missing final usage is not treated as zero cost.
- Local function and custom tools require explicit route capability metadata;
  tool JSON is not blind passthrough and SLAIF does not execute tools.
- Image input requires explicit Responses image-input route capability; it does
  not enable `/v1/files`, file IDs, image generation, audio input/output,
  hosted tools, or stateful Responses.
- File input requires explicit Responses file-input route capability; it does
  not enable `/v1/files`, file IDs, provider-side uploads, file search,
  retrieval tools, Office/spreadsheet formats outside the configured allowlist,
  audio input/output, hosted tools, or stateful Responses. SLAIF does not fetch
  file URLs, parse, OCR, index, extract text from, store, or log file payloads.
- Input-token counting requires explicit
  `capabilities.responses.input_token_count=true`. It does not create a
  Response, does not inject output-token defaults, does not reserve generation
  quota, and does not create a normal generation usage ledger row. Payload
  storage and logging prohibitions are the same as generation requests.
- Key-template revisions may carry a sanitized `responses_policy` summary for
  the implemented stateless local subset. Template-created keys copy only that
  safe summary as provenance metadata; they still require normal key endpoint,
  model, provider, route capability, pricing, and quota checks.
- MCP/connectors are excluded.
- `background`, `store`, `previous_response_id`, conversation/provider-side
  state, retrieval, delete, cancel, and input-item listing are excluded until
  ownership mapping, quota, accounting, and audit behavior are implemented.
- `store=false` is injected before forwarding when omitted.
- Tool-enabled policies, when implemented later, require bounded-overrun cost
  calculations that admins can inspect before enabling the policy.
- Pricing catalog refreshes must be previewed, confirmed, and audited; refreshes
  must never silently replace production pricing rows.
- Provider secrets remain server-side and are never accepted from Responses
  request bodies or dashboard policy forms.
- Plaintext gateway key rules are unchanged.

### Calibration Keys And Usage-Derived Recommendations

Calibration keys are ordinary gateway keys with deliberately lenient limits for
trusted organizers. Admins may analyze their safe usage metadata to recommend
stricter templates for participant keys.

The workflow may use endpoint, provider, model, token-count, tool-count, and
cost metadata. It must not store raw prompts, completions, raw request/response
bodies, raw tool payloads, raw chain-of-thought, plaintext gateway keys,
provider keys, session tokens, password hashes, encrypted payloads, nonces, or
email bodies. Reasoning or thinking token counts are safe operational metadata
when a provider exposes them.

Recommendations are never automatic mutations. An admin must review assumptions
and explicitly confirm any generated template or single-key creation. The
implemented template policy surface covers only safe stateless local Responses
capability summaries; hosted/stateful/multimodal policy and bulk key creation
from templates remain future work.

The central implementation contract is
[`responses-compatibility.md`](responses-compatibility.md).

## Redis Rate Limiting

When enabled, Redis enforces request, estimated-token, and active-concurrency
limits. Active concurrency uses request-specific slots with heartbeat refresh
for long streams and TTL cleanup for crash recovery.

`RATE_LIMIT_FAIL_CLOSED` controls Redis failure behavior. When unset, production
fails closed and development/test fails open. Redis remains fast operational
state; it is not the hard quota source of truth.

Redis outage handling is documented in
[`runbooks/redis-outage.md`](runbooks/redis-outage.md).

## Email And Celery

Asynchronous key delivery uses encrypted `one_time_secrets` rows. Celery task
payloads contain IDs only, such as `one_time_secret_id` and `email_delivery_id`.
They never contain plaintext gateway keys.

Plaintext keys may appear transiently inside the email delivery process because
email is the intended one-time delivery channel. They are not stored in
`email_deliveries`, audit rows, logs, PostgreSQL key rows, or Celery/Redis
payloads. Send-now and enqueue CLI modes suppress plaintext key output because
email/Celery is the selected secret delivery channel.

Email delivery is not mathematically exactly-once because SMTP acceptance and
database finalization are separate systems. The gateway fails closed around that
boundary: before SMTP it persists a `sending` state, SMTP failure before
acceptance records a retryable `failed` status with the one-time secret still
pending, and SMTP success finalizes by consuming the one-time secret and marking
the delivery `sent`. If SMTP may have accepted the message but database
finalization fails, the row is left or marked `ambiguous`; automatic retry is
blocked and operators should rotate the key if receipt cannot be confirmed.

Ambiguous email delivery handling is documented in
[`runbooks/ambiguous-email-delivery.md`](runbooks/ambiguous-email-delivery.md).

## Redaction And Logging

Structured logging redacts configured/custom gateway key prefixes, bearer keys,
provider keys, cookies, passwords, CSRF/session tokens, token hashes, encrypted
payloads, nonces, and nested sensitive metadata across common key naming styles.

Metrics and logs must not contain real secrets. `/metrics` and `/readyz` should
be internal or allowlisted in production. Production startup warnings make risky
exposure overrides visible but do not replace network controls.

## CLI Safety

`slaif-gateway secrets generate ...` creates server/runtime secrets one at a
time for HMAC signing, admin sessions, and one-time-secret encryption. Without
`--write`, the generated value is printed once to stdout for operator capture.
With `--write`, the CLI updates only the requested env variable and does not
print the generated value by default. It refuses to modify `.env.example`,
preserves unrelated env lines, does not create backup files, and requires
`--force` before replacing existing non-placeholder values.

Text-mode key create/rotate commands may show the newly generated plaintext key
once for operator workflows. JSON output is secret-safe by default: operators
must explicitly use `--show-plaintext` or `--secret-output-file` when capturing
the one-time secret outside email delivery.

`--secret-output-file` writes to a new file with restrictive `0600`
permissions. Send-now and enqueue email delivery modes reject additional
plaintext destinations by default. Destructive reserved-counter resets require
explicit confirmation.

## Admin Web Sessions And CSRF

The admin web foundation exposes `/admin/login`, `/admin/logout`, a placeholder
`/admin` dashboard, key list/detail pages under `/admin/keys`, owner,
institution, and cohort list/detail/create/edit pages, provider config pages, model route
pages, pricing pages, and FX list/detail/create/edit pages. The key pages
display safe key metadata only:
prefix, public key ID, hint, owner, status, computed validity state, quotas,
counters, allowed policy summaries, and rate-limit policy. Key detail pages
provide CSRF-protected POST actions to suspend, activate, and permanently revoke
gateway keys through the existing key service and audit behavior.
Owner, institution, and cohort pages display safe record metadata and key count
summaries and provide CSRF-protected create/edit forms for schema-backed record
metadata. These forms require a non-empty audit reason, write safe audit rows
through service-layer logic, reject secret-looking notes/metadata, do not create
keys inline, and do not modify historical usage ledger rows. Delete and
anonymization workflows are intentionally not implemented yet because
owner/institution/cohort records can be linked to historical usage snapshots.
Cohorts are standalone in the current schema; owners can reference institutions
but do not link directly to cohorts. Provider config pages display safe local metadata and provide
CSRF-protected create, edit, enable, and disable forms for provider metadata
only. They may display `api_key_env_var` names, but never provider secret values,
and state changes write safe audit rows through the provider config service.
Model route pages provide CSRF-protected create, edit, enable, and disable forms
for local routing metadata only. Route forms validate exact/prefix/glob match
types, provider config references, priority values, endpoints, and safe metadata;
they may display provider env var names for operator selection, but never
provider secret values. Route state changes write safe audit rows through the
model route service and do not change provider adapter behavior. Pricing pages
provide CSRF-protected create, edit, enable, and disable forms for local pricing
metadata only. Pricing forms parse decimal strings directly, validate
currencies, validity windows, provider references, and safe metadata, and write
safe audit rows through the pricing rule service. Pricing changes may affect
future quota reservation and accounting, but the dashboard does not change the
runtime pricing calculation semantics and does not accept provider secret
values. FX catalog pages provide CSRF-protected create and edit forms for local
FX metadata only. FX forms parse Decimal rates from strings, validate currency
pairs, positive rates, and validity windows, and write safe audit rows through
the FX rate service. FX import preview validates CSV/JSON without mutation, and
confirmed FX import execution re-parses and re-validates server-side, requires
explicit confirmation plus an audit reason, and creates rows only when every row
is a valid supported create. FX changes may affect future EUR conversion, quota
reservation, and accounting, but the dashboard does not change runtime FX lookup
semantics and does not call external FX services. The current FX schema has no
enabled state; active status is controlled by validity windows. Read-only usage, audit, and email delivery pages display
safe activity metadata only. Usage pages do not display prompts, completions, or
raw request/response bodies. Email delivery pages do not display email bodies
because key-delivery email bodies may contain plaintext gateway keys. Audit
metadata is sanitized/redacted before display. These pages do not display
plaintext gateway keys, token hashes, encrypted one-time-secret payloads,
nonces, provider key values, password hashes, admin session tokens, or
prompt/completion content.

Admin passwords are verified with Argon2id password hashes. Successful login
creates a server-side `admin_sessions` row. PostgreSQL stores HMAC-hashed
session and CSRF tokens only; plaintext session tokens are sent only as secure
browser cookies and are not logged or rendered in templates.

Admin session cookies are `HttpOnly`, `SameSite=Lax` by default, and `Secure`
by default in production. Session validation rejects missing, revoked, expired,
or inactive-admin sessions. Logout revokes the server-side session row and
clears the browser cookie.

Admin login is protected by DB/audit-backed failed-attempt rate limiting. The
gateway counts recent failed `/admin/login` attempts by normalized email and
client IP, records failed attempts and temporary lockout events in `audit_log`,
and blocks password verification while the lockout is active. Failure and
lockout messages are generic, do not reveal whether an account exists, and do
not expose exact attempt counts. Redis is not required for this admin control.
Plaintext passwords are never stored, logged, or written to audit metadata.

Current v1 admin authorization treats all active admin users as full operators.
`role=admin` and `role=superadmin` can use the implemented dashboard/operator
actions; `superadmin` is metadata/future-proofing rather than an enforced RBAC
boundary. Inactive admin accounts cannot log in, and revoked or expired
server-side sessions cannot access admin routes. Operators should treat every
active admin account as highly privileged. Future RBAC, superadmin-only
permissions, and MFA may be added later, but they are not implemented in the
current admin surface.

Login and logout forms use CSRF tokens. Login CSRF tokens are signed and paired
with a temporary cookie. Authenticated form CSRF tokens are HMAC-hashed in the
server-side session row. Admin key, owner, institution, cohort, provider, route,
pricing, FX, usage, audit, and email delivery pages use authenticated GET
routes. Key creation, suspend, activate, revoke, validity-window update, hard
quota limit update, usage-counter reset, rotation, owner/institution/cohort
metadata changes, provider config, route, pricing, and FX metadata mutation forms require a valid authenticated session
plus the per-session CSRF token. The dashboard route import preview form
requires CSRF, validates CSV/JSON/TSV rows, verifies provider references against
provider config rows, rejects unknown fields and secret-looking
capabilities/metadata/notes values, and does not write `model_routes`, audit
rows, or uploaded content. Route import execution also requires CSRF, explicit
confirmation, and a non-empty audit reason. It re-parses and re-validates the
submitted upload or pasted content server-side, does not trust preview HTML or
client-side classification, and writes model route rows only after all rows
validate as supported create rows. Invalid, duplicate, conflict, or
update-classified rows block the entire import with no mutation. Successful
creates are audited through the route service. Route import preview/execution
does not call providers, does not store raw uploaded content, and changes future
model resolution only after confirmed local route rows are created. The
dashboard pricing import preview form also
requires CSRF, validates CSV/JSON/TSV rows with Decimal money values parsed from
strings, rejects unknown fields and secret-looking source/notes/metadata values, and
does not write `pricing_rules`, audit rows, or uploaded content. Dashboard
pricing import execution requires CSRF, explicit confirmation, and a non-empty
audit reason. It re-parses and re-validates the submitted upload or pasted
content server-side, does not trust preview HTML or client-side classification,
and writes pricing rows only after all rows validate as supported create rows.
Invalid, duplicate, overlapping, disabled, or update-classified rows block the
entire import with no mutation. Successful creates are audited through the
pricing service. Neither preview nor execution calls external pricing APIs or
providers, stores raw uploaded content, or accepts provider keys. The dashboard
FX import preview form requires CSRF, validates CSV/JSON rows with Decimal
rates parsed from strings, rejects unknown fields, invalid currency pairs,
same-currency pairs, invalid validity windows, non-positive rates, and
secret-looking source/note/metadata values, and does not write `fx_rates`, audit
rows, or uploaded content. Dashboard FX import execution requires CSRF, explicit
confirmation, and a non-empty audit reason. It re-parses and re-validates the
submitted upload or pasted content server-side, does not trust preview HTML or
client-side classification, and writes FX rows only after all rows validate as
supported create rows. Invalid, duplicate, conflict, or update-classified rows
block the entire import with no mutation. Successful creates are audited through
the FX service. FX import preview/execution does not call external FX APIs or
providers, does not accept provider keys, does not store raw uploaded content,
and changes future EUR conversion only after confirmed local FX rows are
created. Dashboard bulk key import preview requires an authenticated admin
session and CSRF token. It validates CSV/JSON key-creation rows, owner
references, optional cohort references, validity windows, hard quota fields,
allowlist policy fields, Redis rate-limit policy fields, email delivery modes,
upload size, row count, and secret-looking input. It is preview-only: no
plaintext keys are generated, no `gateway_keys`, `one_time_secrets`,
`email_deliveries`, or audit rows are written, no Celery tasks are enqueued, no
email is sent, and no providers are called. Dashboard bulk key import execution
requires CSRF, explicit import confirmation, one-time plaintext display
confirmation when browser plaintext will be shown, and a non-empty audit
reason. It re-parses and re-validates the submitted upload or pasted content
server-side, creates gateway keys only after all rows validate, calls the
existing key service, and writes safe key-creation audit rows through that
service. Bulk execution supports `none`, `pending`, and `enqueue` email modes;
bulk `send-now` remains future work and is rejected without mutation. Generated
plaintext keys are shown exactly once on a no-cache result page for `none` and
`pending` rows, are suppressed for `enqueue` rows, and are not stored in
PostgreSQL, audit rows, logs, cookies, server-side sessions, URLs, email
delivery rows, or Celery payloads. Bulk `enqueue` creates encrypted
one-time-secret rows and pending email delivery rows, then queues Celery tasks
with IDs only; SMTP is not called in the admin HTTP request. Dashboard usage and audit CSV exports require an authenticated admin
session, CSRF token, explicit confirmation, and a non-empty audit reason. Export
generation writes a safe audit row, respects the current dashboard filters,
enforces configured row limits, and neutralizes CSV formula injection. Exports
contain metadata only: prompts, completions, raw request/response bodies, email
bodies, plaintext gateway keys, provider key values, token hashes, encrypted
payloads, nonces, password hashes, session tokens, SMTP passwords, and HMAC
secrets are excluded or redacted. Export generation does not mutate usage or
audit rows and does not call providers or external services. Dashboard key creation
only selects existing owners/cohorts, calls the existing key service, and writes
the service audit row. Dashboard key creation and rotation support explicit
email-delivery modes:

- `none` renders a no-cache result page that shows the newly generated plaintext
  key exactly once.
- `pending` creates a pending `email_deliveries` row linked to the encrypted
  one-time secret and still shows the plaintext key exactly once.
- `send-now` sends through `EmailDeliveryService`, records `sending` before
  SMTP, consumes the one-time secret only after SMTP success, records delivery
  status, and suppresses browser plaintext display. Possible SMTP-accepted
  finalization failures become `ambiguous` and are not retried automatically.
- `enqueue` creates a pending delivery row, enqueues the Celery task with IDs
  only, and suppresses browser plaintext display.

Existing pending or failed key email deliveries can be sent now or enqueued from
the email delivery detail page only while the linked one-time secret is present,
pending, unexpired, unconsumed, and valid for key email delivery. These actions
require CSRF plus explicit confirmation, never accept plaintext key input, never
display plaintext keys in the browser, and use the same `EmailDeliveryService`
or ID-only Celery task path as the CLI. Consumed, expired, missing, or
wrong-purpose one-time secrets fail safely; the operator must rotate the key and
create a new delivery instead of resending an old plaintext key. Deliveries in
`sending` or `ambiguous` state also fail closed; operators should confirm receipt
out of band or rotate the key.

Revoke and rotation also require an explicit confirmation field and
dashboard-side audit reason before the key service is called. Validity, hard
quota, usage-counter, and rotation changes call the existing key service and
write audit rows through the same service-layer behavior as the CLI. Dashboard
rotation never displays or resends the old plaintext key, and lost replacement
keys must be rotated again. Dashboard creation and rotation plaintext keys are
not stored in PostgreSQL key rows, audit rows, logs, cookies, server-side
sessions, URLs, email delivery rows, or Celery payloads. The service stores the
key HMAC and encrypted one-time-secret material only. Send-now and enqueue use
email/Celery as the selected secret delivery channel and therefore suppress
browser plaintext display. Celery task payloads contain IDs only, never
plaintext keys, email bodies, encrypted payloads, or nonces. Hard quota
limit updates affect PostgreSQL-backed lifetime cost, token, and request limits;
they do not reset used/reserved counters and are distinct from Redis operational
rate-limit policy. Usage-counter reset does not delete usage ledger rows, and
reserved-counter reset requires a second explicit confirmation because it is an
admin repair action for stale in-flight reservations. These key detail actions
never recover or send old plaintext keys.

## Current Limitations

- Arbitrary old-key dashboard email resend actions are not implemented.
  Bulk key send-now execution is not implemented; bulk dashboard execution
  currently supports `none`, `pending`, and `enqueue`.
  Email-delivery mutation pages are limited to existing one-time-secret-backed
  send-now/enqueue actions.
  Owner, institution, and cohort delete/anonymization workflows are not
  implemented yet. Usage and audit pages remain metadata-only except for
  audited CSV export controls.
  External FX refresh workflows are future work.
- Docker Compose packaging and an optional Nginx example are included for
  local/development service layout and reverse-proxy guidance. They are not a
  production certification; production operators must replace all secrets, run
  migrations explicitly, use HTTPS, and keep `/readyz` and `/metrics` internal
  or allowlisted.
- Native Anthropic API support is not implemented.
- Responses API support is limited to stateless text-output
  `POST /v1/responses` with URL/data URL image input, URL/data URL file input,
  typed SSE streaming, non-streaming local function tools, and non-streaming
  local custom tools; hosted Responses tools, stateful lifecycle routes, file
  IDs, `/v1/files`, file search/retrieval tools, audio input/output, image
  generation, and multimodal Responses output remain future work under
  `docs/responses-compatibility.md`. Embeddings API is not implemented.
- Slack/PagerDuty-specific alert integrations are not implemented yet.
- This project has not completed a formal certification, compliance audit, or
  penetration test.
