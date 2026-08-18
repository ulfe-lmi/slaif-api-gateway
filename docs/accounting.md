# Accounting

This document is the accounting documentation index for reviewers and future
implementation work. It does not add runtime behavior or schema fields.

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
- Ownership-checked Responses and Conversations resource/control calls
  (retrieve/delete/input-item listing, Conversation update, and Conversation
  item create/list/retrieve/delete) do not reserve generation quota or write
  normal generation usage ledger rows.
- Successful accounting finalizes from provider usage/cost where available.
- Final provider usage/cost wins over admission estimates and provisional
  metadata.
- Missing streaming usage is not normal success. It must not be treated as
  zero-cost success or followed by a normal successful terminal marker.
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
- Provider-encrypted Codex reasoning generation/replay requires the independent
  default-off `codex_encrypted_reasoning_replay` key and route capability.
  Encrypted and summary bytes are bounded and counted conservatively as model
  input, while provider final usage/cost remains authoritative. After a stream
  supplies final usage, the gateway finalizes PostgreSQL accounting first,
  verifies the same finalized key/request ledger row, then writes 24-hour
  HMAC-only item/call ownership references before releasing the held
  `response.completed`. Reference-persistence failure emits safe failure and
  suppresses normal completion without releasing or reversing charged usage.
  Missing usage, malformed/error events, and disconnects create no usable
  replay reference. Reference rows are control metadata, never billing truth.
- Fully gated Codex admission replaces only the injected ordinary 1,024 output
  default with the strict route default (32,768 in the qualification profile),
  then enforces route/operator output and context bounds before Redis, pricing,
  quota, or provider work. Ordinary non-Codex admission remains unchanged.
  Gated V1 compact is the deliberate exception: because the pinned client does
  not send `max_output_tokens`, SLAIF keeps that field absent upstream but uses
  the validated route maximum (128,000 in the qualification profile) as the
  effective/requested output exposure for context checks, reservation, pricing,
  and safe admission evidence. Ordinary compact and ordinary Responses retain
  their existing defaults.
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
