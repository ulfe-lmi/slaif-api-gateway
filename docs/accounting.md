# Accounting

> **Authority:** Current PostgreSQL reservation, finalization, cost, and reconciliation contract
> **Not:** Provider-invoice or exact pre-call no-overrun assurance

This document is the accounting contract and evidence index for reviewers. It
describes current behavior but does not itself add runtime behavior or schema
fields.

For RC2 feature-fullness versus implemented-scope verification status, see
[`rc2-feature-scope.md`](rc2-feature-scope.md). Current accounting docs describe
implemented paths only; they cover the bounded Realtime client-secret
admission slice but not full Realtime call/media transport parity.

Current authoritative contracts:

- [`provider-forwarding-contract.md`](provider-forwarding-contract.md) defines
  admission-time quota reservation, provider forwarding order, streaming
  finalization, missing-usage handling, and reconciliation behavior.
- [`security-model.md`](security-model.md) defines security and privacy
  boundaries for quota/accounting, Redis, streaming diagnostics, usage
  profiling, and reconciliation.
- [`database-schema.md`](database-schema.md) defines durable PostgreSQL tables
  and fields.

Core invariants:

- PostgreSQL is authoritative for hard quota, reservations, usage counters,
  ledger rows, and reconciliation state.
- Redis is temporary operational state only. Redis must not become the only
  hard quota or accounting store.
- Cost-bearing provider calls reserve quota in PostgreSQL before forwarding.
- Lazy (wait) throttling, when explicitly stored on a key, waits at the Redis
  operational rate-limit seam before provider work. Waiting reserves no
  quota, writes no ledger row, and holds no PostgreSQL connection or
  transaction; the ordinary PostgreSQL reservation/finalization runs exactly
  once after admission. Hard quota, fence, and hold authority are unchanged.
- Ownership-checked Responses and Conversations resource/control calls
  (retrieve/delete/input-item listing, Conversation update, and Conversation
  item create/list/retrieve/delete) do not reserve generation quota or write
  normal generation usage ledger rows.
- Successful accounting finalizes from provider usage/cost where available.
- Final provider usage/cost wins over admission estimates and provisional
  metadata.
- An explicit route media policy can replace encoded image bytes with a fixed
  allowance or a configurable patch-grid estimate from bounded inline image
  headers. Unknown/remote/animated sources retain the fixed fallback. The same
  estimate feeds context admission, TPM and PostgreSQL reservation, with
  idempotent route revalidation; provider-reported final usage still wins.
  No image content, URLs or decoded headers enter ledger/audit metadata. See
  [media input estimation](media-input-estimation.md).
- Missing streaming usage is not normal success. It must not be treated as
  zero-cost success or followed by a normal successful terminal marker.
- A Local Coding public Responses request uses one ordinary
  `strict_bounded` PostgreSQL reservation and one terminal ledger outcome.
  Local internal compiler/governance capacity does not create Gateway
  accounting rows. Local adapter-managed `tool_search` and `web_search`
  candidates create no hosted-tool fee, external capability or destination,
  fence, hold, provider, or route accounting facts.
- Dual-gated Codex request-envelope admission counts the approved
  provider-forwarded envelope and message-ID material conservatively. Safe
  estimation evidence may contain field names and aggregate byte/token counts,
  never envelope values. Size-capped `client_metadata` is validated and dropped
  before provider forwarding, so it is not provider-billed input. Provider
  final usage/cost remains authoritative.
- Fully key-gated Codex create/compact history may contain pinned
  `internal_chat_message_metadata_passthrough` only on message, reasoning,
  function/custom call and output, or compaction items. A null or canonical JSON
  object of at most 32,768 bytes is validated and discarded before canonical
  input estimation. It contributes zero model-input tokens/bytes and never
  reaches provider input, replay/HMAC material, accounting metadata, safe
  evidence, logs, audits, metrics, or exports. Ordinary, partially gated,
  additional-tools, hosted, and unknown item paths remain rejected.
- Separately gated Codex client-tool declarations count their canonical
  namespace/tool containers, descriptions, function schemas, `exec` grammar,
  and bounded string `tool_choice` as provider/model request input. Pinned
  qualification permits at most 20,000 bytes for each exact child-tool
  description and 32,768 description bytes in aggregate; namespace and
  ordinary function/custom descriptions retain their 4,096-byte limits. Every
  admitted description byte remains part of the conservative estimate. Safe
  evidence contains only approved category names and aggregate
  byte/token/count data, never descriptions, property names, grammar,
  arguments, results, or client identifiers. SLAIF does not execute the tools
  and records no client tool/service cost; provider final usage/cost remains
  authoritative for the model request.
- Codex streaming calls and replayed results require the additional
  `codex_streaming_tool_events` capability on both the key and route. Function
  arguments, `functions.exec` custom input, replay output, reasoning summary/
  text, and message text are transient model input/output only. Admission and
  live-burn estimation count their bounded canonical bytes, but safe evidence
  retains only category/count/byte totals. It never retains call IDs, item IDs,
  arguments, results, reasoning, or message text.
- The exact Codex 0.149 Local stream profile applies ordinary
  `strict_bounded` accounting to the reviewed reasoning/function/message
  lifecycle. A valid terminal response must contain bounded detailed usage and
  no active item or part. Unknown, malformed, incomplete, or disconnected
  streams follow the existing rollback/interrupted-estimate law and never
  become a normal successful ledger row. Validator state is transient and
  contains no persisted content, identifiers, or raw provider events.
- Before that typed Local stream profile runs, the `local-coding-v1` adapter
  applies static raw-byte SSE ceilings: 25,296,903 bytes per line,
  25,573,379 bytes per frame, 25,296,896 joined data bytes, and 2,048 data
  segments. A pre-output framing error uses the existing provider-failure/
  release path; a post-output framing error uses estimated interrupted
  accounting. Both paths finish with zero pending/reserved state, and
  malformed/oversized bytes are excluded from safe accounting metadata.
- In module version `4`, an exact top-level zero-argument function on the
  Codex/Local pair may close with an empty-string argument summary directly
  from the completed output item when the provider omitted both function
  argument events. This changes only stream-shape admission: the same one
  reservation/one terminal ledger lifecycle, final provider usage, replay
  persistence-after-accounting, and zero-pending requirement still apply.
- Source-derived visible Codex 0.149 reasoning is ordinary bounded input
  material. Its optional/null ID, summary, and visible text bytes contribute
  only to the transient request estimate; they do not create replay ownership
  or enter ledger, audit, metric, export, or error data. Non-null encrypted
  reasoning remains on its existing separately gated ID-bound path.
- On the exact Codex 0.149 Local pair, an assistant history
  `output_text` part is ordinary bounded input material. Its UTF-8 text bytes
  contribute to the existing message input estimate and text caps; the text
  remains transient and does not create output authority, replay ownership, or
  any persisted, logged, audited, metered-metadata, or exported content.
- Fully gated Codex function/custom output items may carry the pinned optional
  bounded `id`. When present, its complete canonical bytes are included in
  model-input admission and cost estimation, including the existing item-ID
  estimate, while provider final usage/cost remains authoritative. The ID is
  transient upstream history only: it creates no separate replay/HMAC
  reference and never enters ledger metadata, safe evidence, logs, audits,
  metrics, or exports. Ordinary function/custom outputs continue to reject it.
  Under the exact 0.149 Local pair, an omitted item ID is also accepted only
  after the mandatory call ID resolves to one same-key HMAC replay reference;
  this ownership check completes before reservation/provider work. Each
  admitted continuation still has its own ordinary reservation and ledger row,
  and failed continuations leave zero pending state.
- Codex `additional_tools` declaration bytes are counted in the conservative
  admission estimate for both the 0.149 and 0.162 modules, including the
  optional bounded declaration item ID on 0.149-v5. On the exact
  `codex-0.162-responses-v1 -> local-coding-v1` pair, the bounded upstream
  lowering removes the validated initial declaration prefix from the forwarded
  provider body but changes no admission, estimation, quota reservation,
  ledger, or cost accounting; provider final usage/cost remains authoritative.
- Under the profile-selected positional-update lifecycle (shipped preset
  `codex-0.167.1`, DATA revision `16`; the packaged default and every
  unmodified shipped preset/profile WITHOUT the feature are unchanged),
  Codex create admission estimation is anchored on
  the PREPARED body: the resolved transport's own pure preparation (native
  vLLM codec, shared configured-upstream preparation, or exact canonical)
  is re-run over the lowered body, and the bounded prepared-JSON byte
  calculation (complete prepared input with real IDs once, forwarded
  instructions, and the relevant non-message fields present in the prepared
  body, `ceil(bytes/3)` tokens) replaces the provisional canonical estimate,
  re-anchoring `unadjusted_input_tokens` so later route/media handling and
  revalidation neither accumulate deltas nor restore stale totals. This is
  a conservative byte approximation, not a tokenizer measurement or
  no-overrun promise; raw byte/item/text/schema bounds stay independent and
  always active, and legacy (non-positional) profiles retain their exact old
  estimator and ordering. A prepared body the transport itself would refuse
  fails closed BEFORE any admission side effect (quota, pricing, or provider
  work), preserving the precise fixed representability codes
  (`upstream_llm_bindings_placement_conflict`,
  `vllm_native_wire_identity_collision`) with a generic safe
  `responses_codex_tool_wire_invalid` fallback for other preparation
  failures; provider final usage/cost remains authoritative.
- When a codec transport on an explicit positional-lifecycle request rejects
  a removed/undeclared wire tool, the adapter clears the rejected output and
  preserves the already-PARSED usage/cost/provider metadata with one fixed
  content-free marker. The core settles that parsed usage through the normal
  settlement path and then refuses the response with a fixed 502 before
  replay references, storage, or return: no free release, no double
  finalization, no raw or partly decoded output in exceptions, logs, or
  persistence, and the denied call receives no replay reference.
  `bindings=None` codec parse errors keep their existing legacy handling.
- Provider-encrypted Codex reasoning generation/replay requires the independent
  default-off `codex_encrypted_reasoning_replay` key and route capability.
  Encrypted and summary bytes are bounded and counted conservatively as model
  input, while provider final usage/cost remains authoritative. After a stream
  supplies final usage, the gateway finalizes PostgreSQL accounting first,
  verifies the same finalized key/request ledger row, then writes operator-expiring (365-day default)
  HMAC-only item/call ownership references before releasing the held
  `response.completed` and the buffered replay-bearing event tail. No tool
  lifecycle item is delivered before that durable commit. Reference-persistence failure emits safe failure and
  suppresses normal completion without releasing or reversing charged usage.
  Missing usage, malformed/error events, and disconnects create no usable
  replay reference. Reference rows are control metadata, never billing truth.
- A non-hosted output-limited Responses terminal with reason
  `max_output_tokens` is settled using its authoritative usage, including
  reasoning/cache components, before the terminal is released. Both canonical
  `response.incomplete` and a vLLM completed event with incomplete status keep
  the original status/reason and partial output. This is finalized HTTP usage,
  not a claim that generation completed. Completed validated replay candidates
  retain the same post-settlement ownership checks; unfinished items create
  none. An unfinished replayable item is withheld with a safe stream failure
  after authoritative settlement, rather than delivered without ownership.
  Delivery disconnects after commit do not finalize or charge a second time.
  Missing usage, malformed output or failed settlement retains the
  existing failure/reconciliation path. Hosted web-search settlement is unchanged.
- Fully gated Codex admission replaces only the injected ordinary 1,024 output
  default with the strict route default (32,768 in the qualification profile),
  then enforces route/operator output and context bounds before Redis, pricing,
  quota, or provider work. Ordinary non-Codex requests keep their own defaults.
  Explicit valid output budgets are clipped down to the applicable route and
  operator maxima; smaller requests are never inflated to the default. The
  forwarded limit is the output component used for pricing and reservation.
  Gated V1 compact keeps the unsupported `max_output_tokens` field absent
  upstream and reserves its endpoint-specific configured compact default,
  capped at applicable maxima, rather than the create-route default or maximum.
  Ordinary compact and ordinary Responses retain their own configured defaults.
  The 1,050,000 context and 128,000 output qualification ceilings are configured
  model data, not hardcoded universal limits.
- Codex pricing partitions provider input into cached reads, cache writes, and
  ordinary uncached tokens, and output into ordinary and reasoning tokens.
  Required cache-write and long-context price/multiplier metadata is strict and
  route-model specific. Admission reserves every estimated input/output token
  at the maximum plausible configured rate; finalization charges the disjoint
  provider-reported components and applies the long-context tier to the full
  request only above its configured threshold. Provider-reported OpenRouter
  cost authority is unchanged. SLAIF-calculated cache-write/long-context cost
  remains local conservative accounting, not invoice truth.
- A gated V1 compact response becomes replayable only after final provider
  usage and finalized PostgreSQL accounting. SLAIF then persists only a
  versioned HMAC over the opaque compaction ID plus ciphertext and safe
  ownership/routing metadata. Only after that persistence succeeds does SLAIF
  emit its normal compact success metric and response. Persistence failure is a
  charged safe failure with no normal success metric or response.
  Raw compact history, IDs, ciphertext, prompt-cache keys, and HMACs never enter
  accounting metadata.
- Prompt text, completion text, streamed chunk text, raw request bodies, raw
  response bodies, tool payloads, media payloads, provider keys, plaintext
  gateway keys, token hashes, encrypted payloads, nonces, password hashes,
  session tokens, and email bodies must not be stored for accounting.
- Codex client metadata, prompt-cache keys, message IDs, reasoning request
  values, tool descriptions, schemas, grammar, arguments/results, and encrypted
  reasoning content must not be copied into quota, ledger, audit,
  usage-profile, reconciliation, metric-label, or export metadata. Approved
  cache keys, message IDs, and client-tool declarations may exist transiently
  in the validated provider request only.
- Current RC2 Chat audio support remains part of ordinary Chat Completions
  accounting: audio input to text output and non-streaming audio output reserve
  quota and finalize through the normal PostgreSQL Chat path. Provider aggregate
  usage stays authoritative when available. Optional provider audio-token detail
  may be recorded only as safe usage metadata; audio payloads and generated
  audio bytes are never stored.
- Standalone `POST /v1/audio/speech`, `POST /v1/audio/transcriptions`, and
  `POST /v1/audio/translations` now use their own endpoint permission, route,
  pricing, and finalization path. PostgreSQL remains authoritative. Provider
  usage stays authoritative when present. Speech can finalize from configured
  request pricing or bounded input estimation when provider usage is absent.
  Transcription and translation require provider usage or an explicit configured
  request-pricing fallback; missing required usage does not become zero-cost
  success. Uploaded audio bytes, transcripts, prompt/input text, and generated
  speech bytes are never stored.
- Standalone `POST /v1/embeddings` now uses its own endpoint permission, route,
  pricing, and finalization path. PostgreSQL remains authoritative. Provider
  `prompt_tokens`/`total_tokens` stay authoritative when present. If provider
  usage is absent, SLAIF finalizes through a bounded input-estimated fallback
  instead of zero-cost success. Input strings, token arrays, embedding vectors,
  raw request bodies, and raw provider response bodies are never stored.
- `POST /v1/realtime/client_secrets` now uses its own endpoint permission,
  route, pricing, and admission finalization path. PostgreSQL remains
  authoritative for the issued control-plane request. OpenAI's current Realtime
  docs/SDK state that a client secret can create multiple sessions until it
  expires, that a started session can outlive expiry, and that clients can send
  later session/response overrides. SLAIF therefore does not claim hard actual
  session-usage accounting from client-secret issuance alone. Quota-limited keys
  fail closed unless the route explicitly sets
  `realtime.client_secret_direct_provider_exposure_accepted=true` and the
  pricing row provides a non-refundable `request_price` admission charge.
  Provider usage stays authoritative when present. When provider usage is
  absent, SLAIF finalizes issuance with the safe reason
  `realtime_client_secret_issued`, marks `estimate_is_invoice_grade=false`, and
  records only safe admission metadata. Ephemeral client secrets, instructions,
  raw session config, audio payloads, transcripts, raw SDP, raw events, and
  raw provider bodies are never stored.

## External-tool quota modes and bounded runtime

The versioned contract defines two mechanically testable policy modes. Their
canonical policy is persisted in existing JSON and operator changes are
audited:

- `strict_bounded` is the default. Provider-hosted/external authority is denied;
  existing client-operated tools retain their independent policy and ordinary
  per-model-request accounting.
- `external_tool_fenced` is consumed only for the exact OpenAI Responses
  `provider_web_search` standard-key/route intersection. It requires positive
  finite request, token, and EUR limits, bounded declarations/calls, final
  usage and cost evidence, and literal overrun acknowledgement. Every other
  hosted/external capability remains denied.

The fenced promise is exact: one admitted provider-hosted external-tool request
may exceed the key's remaining token or cost quota before SLAIF regains control.
SLAIF will reject concurrent requests for that key while the request is
unresolved, finalize authoritative provider usage/cost when available, reject
following requests after exhaustion, and retain a blocking accounting hold
when final cost is missing, ambiguous, interrupted, or awaiting reconciliation.
This is not an invoice guarantee or zero-overrun promise.

The exclusive-key fence and full-remaining-balance reservation foundation uses
fence state, a reservation pointer, and timestamps
live on the locked `gateway_keys` row, the locked PostgreSQL key row is the
single concurrency authority (Redis is not), and acquisition atomically
reserves the complete remaining cost, token, and one request of balance in
one `external_tool_fenced` reservation. The fenced reservation persists the
bound provider name and route UUID, and an exact retry matches the key,
request ID, endpoint, requested model, provider, route UUID, capabilities,
destinations, fenced mode, and linked fence facts; changing provider or route
alone is a fixed conflict, never a silent retry. Exclusivity holds in both
lock orders: a fence cannot be acquired while the key carries any pending
reservation or non-zero reserved counter, and an ordinary reservation
cannot be admitted while a committed fence exists. Resolution is authoritative
evidence: it requires exact reservation and ledger ownership and fact
agreement and all reserved counters to be exactly zero before the fence
clears; any mismatch or unreconciled counter leaves the fence in place. The
active retry is read-only after the key lock and requires the pointed
reservation to be pending and owned by that same key; resolution locks the
reservation first and then the key, matching the ordinary quota lifecycle
order, so it never waits on an existing reservation while holding the key. The
foundation is implemented, and the manual hold/reconciliation path is active
for the bounded OpenAI Responses `web_search` runtime. Fence expiry
is an inspection threshold and never means safe release; a committed fence
survives process restart and keeps blocking admission. Emergency suspend or
revoke stops admission but does not settle accounting, and the exact overrun
and one-winner concurrency promise above is implemented for this selected
runtime. Ordinary stale-reservation reconciliation identifies
external-mode pending reservations as requiring external-tool review and never
auto-releases them; see the
[`stale-reservation-reconciliation`](runbooks/stale-reservation-reconciliation.md)
runbook. The same recovery (expired-pending release, external-tool hold
finalize/release, and provider-completed recovery) is also available in the
admin console accounting operations area (G14/216) as a reviewed dry-run ->
signed review -> superadmin confirm-and-apply workflow; see
[`admin-usability.md`](admin-usability.md) and
[`runbooks/admin-access.md`](runbooks/admin-access.md). Fenced policy cannot be stored without positive finite request,
token, and EUR limits, and later limit clearing is rejected before mutation or
audit.

## Chat Completions Streaming Live-Burn Margin

[`streaming-live-burn-margin.md`](streaming-live-burn-margin.md) records a
per-key streaming live-burn margin policy. The implemented runtime slices are
`POST /v1/chat/completions` with `stream=true` and the supported stateless
text-output `POST /v1/responses` streaming subset.

The feature is an operational stream interruption control, not billing truth:

- Chat Completions streaming is implemented.
- Responses typed SSE live-burn is implemented for the supported stateless
  text-output subset and the explicitly gated Codex client-tool event slice.
- The per-key default is enabled with zero cost and token margins.
- Positive margins stop before the quota boundary, zero margins stop near the
  estimated boundary, and negative margins allow bounded estimated overrun.
- Cost and token thresholds are enforced independently; whichever threshold is
  crossed first stops the stream.
- Live estimates are provisional and must not become invoice-grade billing
  truth.
- Provider final usage/cost remains authoritative when available.
- PostgreSQL remains the hard quota/accounting source of truth.
- Redis or in-memory state may hold only temporary live-burn counters or
  metrics.
- No streamed content, prompts, completions, tool payloads, media payloads, raw
  request bodies, or raw response bodies may be stored.
- For the Codex slice, live-burn counts output-text deltas, function-argument
  deltas, custom-tool-input deltas, and reasoning-summary/text deltas. Matching
  done events are not double counted; a bounded done value is counted only when
  no corresponding deltas were seen. The threshold-crossing event is withheld.
- Missing provider usage after an intentional streaming live-burn interruption
  is recorded as estimated interrupted accounting; it is not normal zero-cost
  success.
- If a Chat or Responses stream has already emitted token-bearing output and
  then ends with client disconnect, provider/network error, or missing final
  usage, SLAIF records estimated interrupted accounting instead of fully
  releasing the reservation. Only safe counters and stop reasons are stored.

The persisted safe key metadata shape is:

```json
{
  "chat_streaming_live_burn": {
    "version": 1,
    "enabled": true,
    "cost_margin_eur": "0.000000000",
    "token_margin": 0
  }
}
```

Usage reporting now projects existing safe Chat streaming live-burn ledger
metadata into admin and CLI operator views. `/admin/usage` shows a compact
stopped indicator for triggered Chat streaming rows, usage detail pages show
individual sanitized live-burn fields, `slaif-gateway usage live-burn-summary`
prints aggregate counts, and usage CSV exports include safe live-burn columns.
The reporting source is PostgreSQL usage ledger metadata only. These reports
must not store or render streamed chunks, prompts, completions, tool arguments,
media payloads, raw request bodies, raw response bodies, secrets, or raw
metadata JSON for the live-burn section. Prometheus live-burn counters remain
future work.

### Agent Chat Profile estimate and settlement coverage

A request served under a preprotected agent Chat profile uses the same
admission-time estimation and PostgreSQL settlement boundaries as ordinary
Chat Completions. Input token estimation and cost pre-reservation cover all
material retained in the forwarded body: client-supplied messages (including
the per-profile assistant reasoning fields), tool declarations and their
serialized schemas, in-request tool call arguments and results, and any
other retained serialized object/list fields. The profile adds no new
billing category, pricing row, or ledger column, and provider final
usage/cost remains authoritative when available. Failed provider responses
release the pending reservation and create a failed usage ledger row. A
stream that ends before final usage (client disconnect, provider/network
error, or an intentional live-burn interruption) is finalized as estimated
interrupted accounting when it has positive estimated output; with no
estimated output the pending reservation is released and a failed ledger row
is created (zero charged). The profile pin changes none of these
boundaries.

## External-tool accounting holds

The bounded OpenAI Responses web-search runtime uses the existing PostgreSQL
fence and full-remaining-balance reservation. A successful response finalizes
model token cost plus the configured per-call fee, writes one content-free
ledger, and resolves the fence atomically. External-tool requests with unknown
or ambiguous final accounting use a durable hold: the key fence is `held`, the full pending reservation remains reserved,
and one safe ledger records the bounded reason and evidence quality. Expiry is
not release authority. Only explicit audited manual reconciliation may provide
actual usage/cost or confirm no charge; missing cost never becomes a zero-cost
success. Operator actuals are reconciliation evidence, not invoice truth.

Actual overruns are charged into used counters and later admission is rejected
normally when the key is over limit. Scheduled reconciliation inspects and
alerts on holds but never mutates them. See
`docs/runbooks/external-tool-hold-reconciliation.md`.

## Native module fixed-request billing foundation

Provider configurations with `kind=module` are a bounded foundation for a
reviewed, statically registered native downstream module. The shared
configured completion adapter serves facial scoring and ZAP-IT using the
same fixed-request billing path. A module Chat
Completions route must have a non-null, non-negative `request_price`; token
component prices are ignored for this billing mode. The configured currency is
converted through the existing EUR FX path, so a `0 EUR` request price is an
exact zero-cost estimate.

Module Chat reservations still reserve one request and retain key lifecycle,
request-limit, rate-limit, concurrency, expiry, revocation, and external-tool
fence controls. They reserve zero tokens and therefore do not turn zero price
into unlimited requests. Successful normal Chat finalization records zero
provider usage tokens and the fixed request cost atomically in PostgreSQL.
Provider failure or timeout uses the existing failed-attempt ledger and
reservation-release path.

Streaming, module Responses ingress, content persistence, and dynamic
module/plugin loading remain unsupported. The ZAP-IT profile calling an
upstream Responses facade is still billed as one gateway Chat request, not
as LLM tokens. See [completion services](completion-services.md). Module
credentials remain server-side and are resolved only from the configured
environment-variable name.

## Coherent Admission Capture (pricing and FX)

Admission cost estimation for Chat Completions, standalone Audio,
Embeddings, Realtime client-secret admission, and Responses (including the
pre-fence hosted-tool pricing validation) reads the active pricing row and
the native-to-EUR FX row **in one statement**
(`PricingRulesRepository.find_active_pricing_rule_with_fx`, consumed through
`PricingService.capture_pricing_and_fx`):

- the price side selects exactly the same active enabled row as the
  historical two-step lookup (same validity window, most recent
  `valid_from` first);
- the FX side selects the same rate row as `find_latest_rate` for
  `(base_currency=<price currency>, quote_currency='EUR')` (same window,
  most recent `valid_from` first, `created_at` tie-break);
- EUR-priced rows capture the read-free identity conversion (no FX read);
- fail-closed: a missing pricing rule raises `PricingRuleNotFoundError` and
  a missing non-EUR rate raises `FxRateNotFoundError`, exactly as before.

Why one statement: under READ COMMITTED, the historical two reads (price,
then FX) could straddle a concurrent price+FX supersession and mix an old
price with a new rate (or the reverse), producing a one-off cost estimate
that matches neither complete catalog state. One statement takes one
snapshot, so a concurrent atomic supersession is observed only as the
complete old pair or the complete new pair — never mixed. The captured pair
(`PricingCapture`) is injected into the estimates; the estimates perform no
additional pricing/FX reads when a capture is supplied, and the pre-fence
Responses hosted-tool validation no longer performs a second FX read.

This changes no reservation, finalization, reconciliation, or ledger
semantics: the estimate still reserves the same worst-case cost, provider
usage still wins at finalization, and `convert_to_eur` remains available for
callers that do not capture (including the legacy internal path). See
[Pricing catalog and bounded
overrun](pricing-catalog.md#coherent-admission-capture-and-supersession) for
the supersession side of the same guarantee.


## Hard quota exhaustion errors

Exceeding a key's configured cost, token, or total request quota returns HTTP
429 with `error.type = "insufficient_quota"` and the existing stable
`error.code = "quota_limit_exceeded"`. The safe message identifies the limit;
`error.param` is respectively `cost_limit_eur`, `token_limit_total`, or
`request_limit_total`. This also covers a reservation that would exceed the
remaining quota; it does not imply that the used counter already equals the
limit. Accounting, reservations, and enforcement are unchanged.

Temporary per-window request/token limits and concurrent-request limits retain
`rate_limit_error` and their specific codes. Waiting for a rate window does
not replenish a total quota; an operator must extend or reset it. Client
retry and presentation behavior remains client-specific.

### Requested, effective, and reserved output budgets

For Chat Completions, Responses create, and numeric Realtime admission limits,
a valid positive client limit below the applicable maximum is forwarded and
reserved unchanged. A larger limit is clipped to the maximum, and that same
clipped budget is reserved. Defaults apply only to omitted controls (and null where supported);
they never replace an explicit smaller limit. Original requested values remain
available in Chat/Responses policy facts; cost, quota and rate admission use
the effective value. Chat choice counts multiply the per-choice effective
budget: `estimated input + n * effective output per choice`.

Pricing uses the applicable input/output rates for those same components.
Finalization always uses actual provider usage and releases unused quota
reservation. Realtime admission remains admission-only accounting, not actual
session metering. `/responses/compact` has no supported public output-limit
field and uses its own compact default internally, capped at applicable
maxima. Input/context guards and non-token resource limits are unchanged.
