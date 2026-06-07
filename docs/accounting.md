# Accounting

This document is the accounting documentation index for reviewers and future
implementation work. It does not add runtime behavior or schema fields.

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
- Successful accounting finalizes from provider usage/cost where available.
- Final provider usage/cost wins over admission estimates and provisional
  metadata.
- Missing streaming usage is not normal success. It must not be treated as
  zero-cost success or followed by a normal successful terminal marker.
- Prompt text, completion text, streamed chunk text, raw request bodies, raw
  response bodies, tool payloads, media payloads, provider keys, plaintext
  gateway keys, token hashes, encrypted payloads, nonces, password hashes,
  session tokens, and email bodies must not be stored for accounting.

## Planned Streaming Live-Burn Margin

[`streaming-live-burn-margin.md`](streaming-live-burn-margin.md) records a
planned future milestone for per-key streaming live-burn margins. It is not
implemented in the current repository state.

The planned feature is an operational stream interruption control, not billing
truth:

- Chat Completions is the first intended implementation target.
- Responses typed SSE is the second intended implementation target.
- Live estimates are provisional and must not become invoice-grade billing
  truth.
- Provider final usage/cost remains authoritative when available.
- PostgreSQL remains the hard quota/accounting source of truth.
- Redis may hold only temporary live-burn counters or metrics.
- No streamed content, prompts, completions, tool payloads, media payloads, raw
  request bodies, or raw response bodies may be stored.
- Missing provider usage after an interruption remains incomplete or
  reconciliable according to accounting policy; it is not normal success.

Any implementation PR for live-burn margins must update the active accounting,
compatibility, security, configuration, schema, admin/CLI, and test contracts in
the same PR.
