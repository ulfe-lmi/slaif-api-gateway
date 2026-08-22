# OAP Work Order — 025-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/025-model-qualification-basic-task`
Base: main @ e94a793e2300a2876e9baf96ffbcbaecc1575ceb

## Objective and reason

Record the second-tier model qualification results: basic file-read task.
Two models passed (Nemotron Super, Kimi K3) using Codex CLI tool calls to
read a config file and extract a value. Three models (Luna/Terra/Sol)
could not be qualified at this tier due to two separate issues documented below.

## Verified evidence

### Passing models (tier-2 basic task)

| Model | Exit | Reply | Tool used | Notes |
|---|---|---|---|---|
| nvidia/nemotron-3-super-120b-a12b:free | 0 | ANSWER=25 | exec_command (cat) | Correct value from fixture |
| moonshotai/kimi-k3 | 0 | ANSWER=25 | exec_command (cat) | Correct value from fixture |

Fixture: `/tmp/oap-025-fixture/config.env` contained `MAX_CONNECTIONS=25`.
Both models correctly identified this value using a shell tool call.

### Non-passing models (tier-2)

Luna/Terra/Sol could not complete tier-2 because:

1. The `codex-subscription pro` wrapper ignores `OPENAI_BASE_URL` env var
   and sends requests directly to `api.openai.com`, bypassing SLAIF entirely.
   This means the gateway cannot see or account for these calls.
2. When routed through SLAIF using a custom provider profile
   (`model_provider = "slaif_openai"` with `base_url = http://localhost:8000/v1`),
   the gateway's streaming validator rejects one or more SSE event fields that
   OpenAI's Responses API emits but `providers/streaming.py` does not expect.
   Error: `"Provider emitted a Responses streaming event that is not supported
   by this gateway."` (code: `responses_stream_event_not_supported`).

This is a gateway defect in the same class as objective 023-b (vLLM SSE
compatibility), but affecting OpenAI's own SSE stream shape rather than vLLM's.
It requires a continuation round (025-b) scoped to fixing the streaming validator.

## Scope

1. Add a "Codex CLI model qualification — tier-2 basic task" section to
   `docs/compatibility-matrix.md` documenting the two passes and three
   non-passes with root cause.
2. No application code changes in this round. The streaming fix is 025-b.

## Allowed paths

```
docs/compatibility-matrix.md
oap/orders/025-a-model-qualification-basic-task.md
oap/reports/025-a-model-qualification-basic-task.md
oap/active
```

## Non-goals

No streaming validator fix (that is 025-b).
No new profile registration.
No vision qualification (that is 026+).
No auth-passthrough feature.

## Observable acceptance

- Compatibility matrix documents all five models' tier-2 status honestly.
- Root cause for non-passes is stated without ambiguity.
- `git diff --check` passes; CI green on final head.

## Verification

```bash
git diff --check
grep 'tier-2' docs/compatibility-matrix.md
```

## OAP contract

Objective `025-a` creates one PR; remediation uses `025-b`–`025-z` same PR.
Coding agent never merges.
