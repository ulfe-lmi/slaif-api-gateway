# Real-provider qualification

Objective 140 recorded bounded, opt-in, secret-safe real-provider evidence
through SLAIF using `scripts/verify_real_provider_qualification.py`.

## OpenRouter

- Model: `nvidia/nemotron-3-super-120b-a12b:free`
- Non-streaming Chat Completions: HTTP 200; ledger input 23 / output 16 / total 39.
- Streaming Chat Completions: SSE completed with `[DONE]`.
- Non-streaming Responses: HTTP 200; ledger input 23 / output 32 / total 55.

## OpenAI Pro

- Model: `gpt-5.6-luna`
- Non-streaming Chat Completions: HTTP 200; ledger input 12 / output 5 / total 17.
- Streaming Chat Completions: SSE completed with `[DONE]`.
- Non-streaming Responses: HTTP 200; ledger input 12 / output 6 / total 18.

All requests were strictly sequential with ≥15-second gaps. Total request count
was within the ten-request bound. PostgreSQL `usage_ledger` rows were finalized
and pending reservations were zero after each provider run. No API key,
prompt text, or completion text was persisted in this documentation.

## Operational setup notes

The existing qualification routes were Responses-only. This round added
Chat Completions routes and zero-cost Chat pricing for the selected models so
both adapters could be exercised through the gateway. These local database
changes were operator setup only and are not committed as data.
