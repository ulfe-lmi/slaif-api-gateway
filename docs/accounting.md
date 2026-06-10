# Accounting

This document is the accounting documentation index for reviewers and future
implementation work. It does not add runtime behavior or schema fields.

For RC2 feature-fullness versus implemented-scope verification status, see
[`rc2-feature-scope.md`](rc2-feature-scope.md). Current accounting docs describe
implemented paths only; they do not mean Realtime audio or embeddings are
already implemented.

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
- Prompt text, completion text, streamed chunk text, raw request bodies, raw
  response bodies, tool payloads, media payloads, provider keys, plaintext
  gateway keys, token hashes, encrypted payloads, nonces, password hashes,
  session tokens, and email bodies must not be stored for accounting.
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

## Chat Completions Streaming Live-Burn Margin

[`streaming-live-burn-margin.md`](streaming-live-burn-margin.md) records a
per-key streaming live-burn margin policy. The implemented runtime slices are
`POST /v1/chat/completions` with `stream=true` and the supported stateless
text-output `POST /v1/responses` streaming subset.

The feature is an operational stream interruption control, not billing truth:

- Chat Completions streaming is implemented.
- Responses typed SSE live-burn is implemented for the supported stateless
  text-output subset only.
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
