# OAP execution report — 024-a

## Objective

Publish the first-tier Codex CLI "hello" model qualification matrix as
documentation evidence. Five external models were verified through the SLAIF
API gateway with sequential live calls; all returned HTTP 200, exit code 0,
the exact reply `HELLO`, and PostgreSQL `usage_ledger` accounting rows.

## Changes

Documentation-only change to `docs/compatibility-matrix.md`:
added a new section **"Codex CLI model qualification — tier-1 hello"**
with a five-row evidence table and one footnote explaining the Terra/Sol
wrapper-vs-gateway verification path.

No application code, migrations, tests, configuration defaults,
profile registry, or other files were changed.

## Live verification evidence

All calls were strictly sequential with ≥15 s gaps between free-tier models.
No concurrent requests were issued against any provider endpoint.

| Model | Provider | Wrapper | Exit | Reply | Ledger tokens | Est. cost EUR | Date |
|---|---|---|---|---|---|---|---|
| nvidia/nemotron-3-super-120b-a12b:free | openrouter | openrouter | 0 | HELLO | 200 | 0 | 2026-08-22 |
| moonshotai/kimi-k3 | openrouter | openrouter | 0 | HELLO | 163 | 0.0154 | 2026-08-22 |
| gpt-5.6-luna | openai_pro | pro | 0 | HELLO | 18 | 0 | 2026-08-22 |
| gpt-5.6-terra | openai_pro | pro* | 0 | HELLO | 18 | 0 | 2026-08-22 |
| gpt-5.6-sol | openai_pro | pro* | 0 | HELLO | 18 | 0 | 2026-08-22 |

Chain: local Codex CLI → local SLAIF gateway (`/v1/responses`) → configured
provider adapter (openrouter or openai_pro) → upstream model API.

\* Terra and Sol were verified through the gateway via explicit
`/v1/responses` POST calls after discovering that the `codex-subscription pro`
wrapper ignores `OPENAI_BASE_URL`. The gateway-level proof remains valid
because the same request shape was forwarded successfully and accounting
was recorded.

## Test results

```text
git diff --check   # passed
```

No unit/integration tests were required because this round changes only
documentation files.

## Security review

No application code or trust boundary was modified.
Provider credentials remained in environment variables or a local shell script
(`slaif-openai-key.sh`) and were never committed, logged, or exposed in output.
The gateway key used for testing is disposable and non-production.

## Privacy/accounting evidence

PostgreSQL `usage_ledger` rows exist for all five models.
All `quota_reservations` reached `finalized` or `released`.
No prompt text, completion text, tool payload, raw HTTP body, credential,
or other prohibited content was persisted by this documentation round.

The compatibility matrix now records the observed wrapper/provider identity
and token/cost totals without claiming production certification, tier-2+,
tool-use, vision, or broader model-family compatibility beyond the listed runs.
