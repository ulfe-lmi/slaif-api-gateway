# Real-provider qualification boundary

> **Status:** Historical partial evidence; no current complete real-provider accounting qualification
> **Audience:** Maintainers and independent reviewers

Real-provider qualification is separate from mocked adapter conformance and the
disposable production-appliance provider-double matrix. It must prove that a
request traversed the Gateway, reached the selected real provider, terminated
with supported usage, and correlated to PostgreSQL reservation/accounting truth.

## Historical Objective 140 evidence

Objective 140 recorded six bounded calls through a locally configured Gateway:

| Provider | Flow | Recorded result |
|---|---|---|
| OpenRouter | Chat non-streaming | HTTP 200; 23 input, 16 output, 39 total tokens |
| OpenRouter | Chat streaming | SSE reached `[DONE]` |
| OpenRouter | Responses non-streaming | HTTP 200; 23 input, 32 output, 55 total tokens |
| OpenAI | Chat non-streaming | HTTP 200; 12 input, 5 output, 17 total tokens |
| OpenAI | Chat streaming | SSE reached `[DONE]` |
| OpenAI | Responses non-streaming | HTTP 200; 12 input, 6 output, 18 total tokens |

The immutable historical report states that ledger rows were finalized and
pending reservations were zero. However, the verifier committed on `main`:

- accepts no PostgreSQL connection or key identifier;
- performs no SQL query;
- emits no request ID or usage for Chat streaming; and
- does not exercise Responses streaming.

The repository therefore cannot independently reproduce the report's database
claims from that verifier. Treat Objective 140 as historical transport evidence,
not complete current accounting qualification.

## What complete qualification requires

A current qualification must use a disposable Gateway and PostgreSQL database
and, for both OpenAI and OpenRouter, exercise:

1. Chat Completions non-streaming;
2. Chat Completions streaming with terminal `[DONE]` and usage;
3. Responses non-streaming; and
4. Responses streaming with exactly one valid `response.completed` usage event.

Each flow must expose a Gateway-generated diagnostic ID that selects exactly one
terminal quota reservation and one matching terminal usage-ledger row. The run
must prove no pending reservation/reserved counters remain, provider retries are
bounded as authorized, stored usage matches the response, and durable metadata
contains no keys or probe content.

Until such an immutable eight-flow result is merged, documentation must say
**real-provider accounting qualification: not complete**.

## Related evidence

- [Production-appliance qualification](verification/2026-08-24-production-appliance-qualification.md)
  proves production Compose, NGINX, PostgreSQL, Redis, provider-double transport,
  accounting, failure, privacy, and cleanup boundaries without a real provider.
- [Provider forwarding contract](provider-forwarding-contract.md) defines the
  credential-replacement and adapter behavior proven deterministically in tests.
- [Accounting contract](accounting.md) defines the PostgreSQL terminal state a
  real-provider run must verify.

None of these records is a model-quality evaluation, provider invoice audit,
production certification, compliance attestation, or SLA.
