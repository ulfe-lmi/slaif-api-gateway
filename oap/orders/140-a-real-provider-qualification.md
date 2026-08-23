# OAP Work Order — 140-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/140-real-provider-qualification`
Base: main @ 6ba8f84acc4b

## Objective and reason

Produce bounded, opt-in, secret-safe real-provider qualification evidence for
the OpenAI and OpenRouter adapters through the SLAIF gateway with full
accounting finalization. This closes the gap identified in
`oap/MVP-CLOSURE-AUDIT.md` where no immutable OAP report records real-provider
evidence for either adapter.

## Human-authorized live targets (explicit approval received)

The human has authorized these exact debug/development targets:

- **OpenRouter** (`https://openrouter.ai/api/v1`):
  - API key already in `.env` as `OPENROUTER_API_KEY`
  - Models: `nvidia/nemotron-3-super-120b-a12b:free` (free) and `moonshotai/kimi-k3`
- **OpenAI API** (`https://api.openai.com/v1`):
  - API key stored in `/home/ubuntu/codex-work/slaif-openai-key.sh` (sourced at runtime)
  - Model: `gpt-5.6-luna` or `gpt-5.6-sol`

### Hard constraints

- Bounded: max 10 requests total across all providers.
- Expected cost: <$0.05 total.
- All calls strictly sequential.
- ≥15 s gap between calls to free-tier models.
- No concurrent requests against any single provider endpoint.
- Provider credentials NEVER enter repository artifacts, CI logs, reports, fixtures, or committed configuration.
- No prompt/completion content persisted beyond existing accounting metadata.

## Scope

1. Create `scripts/verify_real_provider_qualification.py`:
   - Accepts env vars for gateway base URL, gateway key, and provider selection.
   - For each selected provider:
     a. Non-streaming Chat Completions through SLAIF → verify HTTP 200, content, usage_ledger entry.
     b. Streaming Chat Completions through SLAIF → verify SSE completes with `[DONE]`, usage_ledger entry.
     c. Non-streaming Responses through SLAIF → verify HTTP 200, output, usage_ledger entry.
   - Prints structured `RESULT=key=value` lines including `REAL_PROVIDER_CALLED=true`.
2. Execute the script against both providers and capture sanitized output as evidence.
3. Record results in `docs/real-provider-qualification.md`.

## What does NOT count as completion

- A mocked upstream returning OpenAI-shaped JSON.
- A direct call to api.openai.com without going through SLAIF.
- A test that only checks HTTP status without verifying usage_ledger entry.
- Evidence that includes raw API keys.

## Allowed paths

```
scripts/verify_real_provider_qualification.py
docs/real-provider-qualification.md
oap/orders/140-a-real-provider-qualification.md
oap/reports/140-a-real-provider-qualification.md
oap/active
```

## Verification

```bash
# Operator runs this locally with credentials sourced externally
OPENAI_API_KEY=<gateway-key> OPENAI_BASE_URL=http://localhost:8000/v1 \
  .venv/bin/python scripts/verify_real_provider_qualification.py --provider openrouter
OPENAI_API_KEY=<gateway-key> OPENAI_BASE_URL=http://localhost:8000/v1 \
  .venv/bin/python scripts/verify_real_provider_qualification.py --provider openai
```

## Acceptance

Script exits 0; REAL_PROVIDER_CALLED=true for each tested adapter;
usage_ledger entries verified; sanitized evidence committed; all CI green;
report-only SELF commit; never merge.
