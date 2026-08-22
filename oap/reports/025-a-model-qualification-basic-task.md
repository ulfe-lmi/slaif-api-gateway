# OAP execution report — 025-a

## Objective

Record the second-tier Codex CLI basic file-read qualification evidence:
two models passed and three could not be qualified due to documented root causes.

## Changes

Documentation-only change to `docs/compatibility-matrix.md`:
added a **"Codex CLI model qualification — tier-2 basic task"** section with
five model rows and explicit non-pass root causes.

No application code changes.

## Live verification evidence

### Passing models

| Model | Exit | Reply | Tool used | Notes |
|---|---|---|---|---|
| nvidia/nemotron-3-super-120b-a12b:free | 0 | ANSWER=25 | exec_command (cat) | Correct value from fixture |
| moonshotai/kimi-k3 | 0 | ANSWER=25 | exec_command (cat) | Correct value from fixture |

Fixture: `/tmp/oap-025-fixture/config.env` contained `MAX_CONNECTIONS=25`.
Both models correctly identified this value using a shell tool call.

### Non-passing models

Luna/Terra/Sol could not complete tier-2 because:

1. The `codex-subscription pro` wrapper ignores `OPENAI_BASE_URL` and sends
   requests directly to `api.openai.com`, bypassing SLAIF entirely.
2. When routed through SLAIF using a custom provider profile, the gateway's
   streaming validator rejects OpenAI Responses SSE event fields that are not
   currently expected (`responses_stream_event_not_supported`).

## Test results

```text
git diff --check   # passed
```

No unit/integration tests were required because this round changes only
documentation files.

## Security review

No application code or trust boundary was modified.
Provider credentials remained in environment variables or local shell scripts
and were never committed, logged, or exposed in output.

## Privacy/accounting evidence

PostgreSQL `usage_ledger` rows exist for all calls that traversed SLAIF.
All `quota_reservations` reached `finalized` or `released`.
No prompt text, completion text, tool payload, raw HTTP body, credential,
or other prohibited content was persisted by this documentation round.

The compatibility matrix now records the observed wrapper/provider identity
and honest non-pass root causes without claiming broader compatibility beyond
the listed runs.
