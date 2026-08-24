# Real-provider qualification boundary

> **Status:** Historical partial evidence; no current complete real-provider accounting qualification
> **Audience:** Maintainers and independent reviewers

Real-provider qualification is separate from mocked adapter conformance and the
disposable production-appliance provider-double matrix. It must prove that a
request traversed the Gateway, reached the selected real provider, terminated
with supported usage, and correlated to PostgreSQL reservation/accounting truth.
It is a bounded evidence workflow, not a normal test suite or a
production-readiness claim.

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
claims from that verifier. Treat Objective 140 as historical transport
evidence, not complete current accounting qualification. The provider
adapters' exact replacement of the client Authorization value is supported by
deterministic transport tests in
`tests/unit/test_provider_headers.py`,
`tests/unit/test_openai_provider_streaming.py`, and
`tests/unit/test_openrouter_provider_streaming.py`. A live provider cannot echo
or independently attest to the received Authorization header; authenticated
success plus PostgreSQL correlation proves the real adapter path executed, not
provider header attestation.

## What complete qualification requires

A current qualification must use a disposable Gateway and PostgreSQL database
and, for both OpenAI and OpenRouter, exercise:

1. Chat Completions non-streaming;
2. Chat Completions streaming with terminal `[DONE]` and usage;
3. Responses non-streaming; and
4. Responses streaming with exactly one valid `response.completed` usage event.

Each flow must expose a Gateway-generated diagnostic ID that selects exactly
one terminal quota reservation and one matching terminal usage-ledger row. The
run must prove no pending reservation/reserved counters remain, provider
retries are bounded as authorized, stored usage matches the response, and
durable metadata contains no keys or probe content.

Until such an immutable eight-flow result is merged, documentation must say
**real-provider accounting qualification: not complete**.

## Objective 152-a guarded verifier

Objective 152-a implemented a fail-closed verifier for exactly eight sequential
Gateway requests: non-streaming and streaming Chat Completions and Responses
for each of OpenAI and OpenRouter. It requires explicit live authorization,
fresh protected inputs, an HTTPS Gateway at exactly `/v1`, a disposable
loopback PostgreSQL database at the current migration head, bounded output and
cost, and no retry path. It validates stream terminals, usage, Gateway
diagnostic IDs, one finalized reservation, and one matching usage-ledger row
per flow, with bounded privacy-safe output.

The 152-a verifier and its deterministic fake HTTP/SQL tests made no real
provider call. Synthetic tests do not qualify a provider, so the live matrix
remained **NOT RUN** after 152-a.

## Objective 152-b isolation and bounded-output hardening

Objective 152-b remained implementation-only. It required a canonical fresh
Gateway key with zero history, rejected old, concurrent, foreign, or
uncorrelated rows, closed protected-file and parent-symlink bypasses, bounded
serialized output and cost vocabulary, and distinguished attempted Gateway
requests from correlated completed flows. It added no provider call, Gateway
request, PostgreSQL connection, or live qualification. The eight-flow live
matrix therefore remained **NOT RUN**.

## Objective 152-c authorized live result

Objective 152-c performed one authorized live verifier attempt through a fresh
production-Compose Gateway. The verifier attempted only the first ordered flow:
OpenAI Chat Completions, non-streaming. That flow reached HTTP 200 and
finalized in PostgreSQL, but verification stopped at the correlation metadata
boundary with `correlation_metadata_invalid`, reporting
`attempted_requests=1`, `correlated_completed_count=0`, and
`real_provider_call_proven=false`.

The other seven flows were not run. There was no provider retry, selective
rerun, second verifier invocation, or qualification. Bounded SQL evidence
recorded one finalized successful reservation/ledger pair with 36 total tokens
and zero pending/reserved state. That single row is partial failed-live
evidence and cannot be promoted to an eight-flow result. The immutable details
are in the [152-c OAP report](../oap/reports/152-c-authorized-live-gateway-accounting-qualification.md).

## Objective 152-d verifier JSON/JSONB boundary fix

Objective 152-d fixed only the verifier-side asyncpg JSON/JSONB boundary exposed
by 152-c. Its private connection registers explicit text codecs for `json` and
`jsonb` in `pg_catalog` before any schema or data query. The strict decoder
requires valid UTF-8, rejects duplicate object keys, non-standard numeric
constants, arbitrary values, and values larger than 64 KiB, and returns
ordinary Python structures. Codec setup failure closes the connection before
any query or Gateway traffic.

Correlation and privacy validation normalize asyncpg-like JSON strings and
decoded mappings through the same bounded rules, require object metadata, reject
malformed/list/scalar/boolean/duplicate-key/oversized/canary inputs, and
preserve the allowlisted cost source/confidence vocabulary. The focused 152-d
tests use fake asyncpg-like state; no credential was read, no HTTP request was
made, and no SQL connection or provider execution occurred. The immutable
details are in the [152-d OAP report](../oap/reports/152-d-asyncpg-jsonb-correlation-fix.md).

## Current Objective 152 status

No replacement live matrix ran after the 152-d fix. The authorized 152-c
attempt remains one failed partial flow, and the remaining seven flows have not
been exercised. Therefore **real-provider accounting qualification: not
complete**. The verifier and its deterministic evidence are useful tooling,
but neither synthetic checks nor guarded dry runs constitute live provider
evidence.

## Related evidence

- [Production-appliance qualification](verification/2026-08-24-production-appliance-qualification.md)
  proves production Compose, NGINX, PostgreSQL, Redis, worker/scheduler,
  provider-double transport, accounting, failure, privacy, and cleanup
  boundaries without a real provider.
- [Provider forwarding contract](provider-forwarding-contract.md) defines the
  credential-replacement and adapter behavior proven deterministically in tests.
- [Accounting contract](accounting.md) defines the PostgreSQL terminal state a
  real-provider run must verify.

None of these records is a model-quality evaluation, provider invoice audit,
production certification, compliance attestation, support commitment, or SLA.
