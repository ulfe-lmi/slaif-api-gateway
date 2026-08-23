# OAP execution report — 140-a

Implementation head SHA: 0a2f372e946729ff38cd256d978e7852bf24104e
Report publication commit: SELF

## Objective and scope

Produced bounded, opt-in, secret-safe real-provider qualification evidence
through SLAIF for both adapters using
`scripts/verify_real_provider_qualification.py`.

All calls were strictly sequential with ≥15-second gaps. Total request count was
six across both providers (within the ten-request bound). No API key, prompt,
or completion content was persisted in repository artifacts.

## OpenRouter evidence

- Model: `nvidia/nemotron-3-super-120b-a12b:free`
- Non-streaming Chat Completions: HTTP 200; ledger input 23 / output 16 / total 39.
- Streaming Chat Completions: SSE completed with `[DONE]`.
- Non-streaming Responses: HTTP 200; ledger input 23 / output 32 / total 55.

## OpenAI Pro evidence

- Model: `gpt-5.6-luna`
- Non-streaming Chat Completions: HTTP 200; ledger input 12 / output 5 / total 17.
- Streaming Chat Completions: SSE completed with `[DONE]`.
- Non-streaming Responses: HTTP 200; ledger input 12 / output 6 / total 18.

PostgreSQL `usage_ledger` rows were `finalized` with `success=true`; pending
reservations were zero after each provider run. The verifier printed
`REAL_PROVIDER_CALLED=true`, sanitized structured evidence lines, and exited 0
for both providers.

## Operational setup

The existing qualification routes were Responses-only. Local operator setup added
Chat Completions routes and zero-cost Chat pricing for the selected models so both
adapters could be exercised through the gateway. This was disposable database
configuration and is not committed as data.

An initial OpenAI failure was caused by upstream rejection of legacy `max_tokens`;
the verifier now uses `max_completion_tokens`. No repository secret entered any
artifact. `git diff --check` and Ruff passed.

All ten final-head GitHub checks were verified successful on implementation head
`0a2f372e946729ff38cd256d978e7852bf24104e`.

The report is the sole file in this subsequent report-publication commit. No merge was performed.
